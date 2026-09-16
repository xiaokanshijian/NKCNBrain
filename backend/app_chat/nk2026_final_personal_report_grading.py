#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
NK2026 主题小组个人课设报告期末综合批改脚本。

在 本地backend 目录下执行：

  # 仅补 A 梯子图（不覆盖其它已生成卡）
  python app_chat/nk2026_final_personal_report_grading.py --only-a

  # 第①步 S5素材* 卡补齐 keyWords/score/reason/scoreSFT（D/F 手动卡已在系统内 add，跳过）
  python app_chat/nk2026_final_personal_report_grading.py --backfill-metadata

  # 分步
  python app_chat/nk2026_final_personal_report_grading.py --step prep
  python app_chat/nk2026_final_personal_report_grading.py --step 1
  python app_chat/nk2026_final_personal_report_grading.py --step 3

说明：
  - 批改要求「输入类别」字母（见 docs/今年2026…md 表）：
        主材料=拼接PDF；A=梯子图梳理卡；B1～B5=周教研/种子/激励/TA/规划梳理卡；
        C=前序S5综合批改梳理卡；D=去年2025概况卡；E=授课凝练卡（contentTitle：S5素材E:）；
        F=今年2026批改要求卡；G=场景预置文档相关搜索片段（非卡片，第③步 RAG 注入）
  - 第①步产出：S5素材A/B1～B5/C + S5素材E（授课凝练）
  - 第②步手动加卡：D（去年2025…）、F（今年2026批改要求）
  - 第③步：20 组最终综合批改卡（writer：车联 yq / 纸联 2112557 / 体联 lxz）

模型回退：claude-opus-4.8(cloudapi)×2 → gemini-3.1-pro-preview(dmxapi)×2 → deepseek-v4-flash×2
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

_BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangoProject.settings")

import django  # noqa: E402

django.setup()

from openai import OpenAI  # noqa: E402

from app_chat.automation_nk2026 import (  # noqa: E402
    NK2026_SCENE_NAME,
    incentive_group_from_filename,
    matches_incentive_talk_filename,
    max_week_markers_in_filename,
    nk2026_matches_b_planning_xml_log_gxx,
    nk2026_matches_group,
    nk2026_group_role_line,
    theme_keyword_in_text,
    week_num_from_filename,
)
from app_chat.card_analyzer import analyze_card_with_new_standard  # noqa: E402
from app_chat.group_twin_gxx import _read_pre_summary_for_doc  # noqa: E402
from app_chat.models import Card  # noqa: E402
from app_chat.views_card_html import _is_ladder_fill_image_filename  # noqa: E402

C_SCENE_DOCS = (
    "A0监控表.pdf",
    "课程设计中课设实验精进（相关文件的）必要补充说明.pdf",
    "NK2026嵌入式课程目标分解与实施框架(助教专用)-20260309.pdf",
    "嵌入式系统课设各主题助教&教师教研激荡.pdf",
)

_LOG_LOCK = threading.Lock()

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

NOTEBOOK_USERNAME = "testlyf_2026tizitu-group"
LECTURE_USERNAME = "testlyf_demoFeis"
REAL_NAME = "testlyf"
BOOK_NAME = "2026tizitu-group"

# 第③步最终批改卡 writer（按主题）
THEME_STEP3_WRITERS: Dict[str, str] = {
    "车联": "yq",
    "纸联": "2112557",
    "体联": "lxz",
}

THEME_GROUPS: Dict[str, List[int]] = {
    "车联": [2, 3, 4, 5],
    "纸联": [7, 8, 9, 10, 11, 12, 13, 14],
    "体联": [15, 16, 17, 18, 19, 20, 21, 22],
}
GROUP_THEME: Dict[int, str] = {g: t for t, gs in THEME_GROUPS.items() for g in gs}

TITLE_2025 = "去年2025个人课设报告批改各主题大致情况"  # 批改要求 D 类
TITLE_2026_REQ = "今年2026小组个人课设报告批改要求"  # 批改要求 F 类
TITLE_LECTURE = "S5素材E:授课课设三类知识关联凝练"  # 批改要求 E 类

TITLE_B1 = "S5素材B1:周教研助教关注点周次变化梳理"
TITLE_B2 = "S5素材B2:精进种子周次版本推进梳理"
TITLE_B4 = "S5素材B4:TA助教小结周次涌现问题梳理"

MAX_GROUP_CONCURRENT = 3
# 第①步素材拼接：本子内各周尽量完整收集（文字量可控，不做人为只取末周）
STEP1_MATERIAL_CAP = 2_000_000
STEP3_INPUT_CAP = 300_000
STEP3_CAP_REDUCE_DELTAS = (30_000, 30_000, 30_000, 30_000, 30_000)  # 报错后每次减3万，非砍半

# 小组整体组分（百分制）→ 5分制基准；各角色可合理上下浮动，以持平/下调为主
GROUP_SCORE_INFO: Dict[int, Dict[str, Any]] = {
    2: {"grade": "B+", "percent": 87, "score5": 4.35},
    3: {"grade": "A", "percent": 91, "score5": 4.55},
    4: {"grade": "A+", "percent": 93, "score5": 4.65},
    5: {"grade": "A", "percent": 91, "score5": 4.55},
    7: {"grade": "A+", "percent": 93, "score5": 4.65},
    8: {"grade": "B+", "percent": 87, "score5": 4.35},
    9: {"grade": "A-", "percent": 90, "score5": 4.50},
    10: {"grade": "A+", "percent": 93, "score5": 4.65},
    11: {"grade": "B", "percent": 85, "score5": 4.25},
    12: {"grade": "A", "percent": 91, "score5": 4.55},
    13: {"grade": "B", "percent": 85, "score5": 4.25},
    14: {"grade": "A", "percent": 91, "score5": 4.55},
    15: {"grade": "A", "percent": 91, "score5": 4.55},
    16: {"grade": "B+", "percent": 87, "score5": 4.35},
    17: {"grade": "A++", "percent": 95, "score5": 4.75},
    18: {"grade": "A+", "percent": 93, "score5": 4.65},
    19: {"grade": "B", "percent": 85, "score5": 4.25},
    20: {"grade": "A+", "percent": 93, "score5": 4.65},
    21: {"grade": "B", "percent": 85, "score5": 4.25},
    22: {"grade": "B+", "percent": 87, "score5": 4.35},
}

GROUP_ARCHETYPE_W13_15 = """
【近三周 W13/W14/W15（W15 为课设实验整体收尾周；当前批改在期末考试之后）各组组型】
（橄榄-＜橄榄型＜橄榄+＜萝卜-＜萝卜型＜萝卜+＜苹果-＜苹果型＜苹果+，苹果+为最优）
【车联】
2组 上上周W13比萝卜+稍低，上周W14回到萝卜+，本周W15降回比萝卜+稍低
3组 上上周萝卜+，上周提升介于萝卜+和苹果-之间，本周接近苹果-
4组 上上周苹果-，上周提升到苹果型，本周最终比苹果型稍高
5组 上上周接近苹果-，上周降为接近萝卜+，本周回到接近苹果-
【纸联】
7组 上上周W13苹果型，上周W14比苹果型略高，本周W15基本稳定在苹果型
8组 上上周萝卜+略高，上周提升到比萝卜+略高，本周基本维持上周
9组 上上周萝卜+，上周比萝卜+略高，本周提升到苹果-
10组 上上周苹果-，上周接近苹果型，本周提升到苹果型
11组 上上周萝卜+，上周仅基本维持，本周不升反降为萝卜型，未和TA打招呼擅自离场
12组 上上周苹果-，上周接近苹果型，本周基本保持接近苹果型
13组 上上周萝卜型，上周保持萝卜型，本周提升到萝卜+
14组 上上周萝卜+，上周接近苹果-，本周提升到苹果-
【体联】
15组 上上周W13萝卜+，上周W14高于萝卜+一些，本周W15基本保持萝卜+和苹果-之间
16组 上上周萝卜型，上周提升到比萝卜+稍高，本周基本保持萝卜+和苹果-之间
17组 上上周苹果型，上周略高于苹果型，本周提升到接近苹果+
18组 上上周苹果型，上周略高于苹果型，本周提升到接近苹果+
19组 上上周萝卜-，上周到达萝卜型，本周进一步提升到萝卜+，内容愿意做且质量在提升
20组 上上周比萝卜+高一些，上周接近苹果-，本周基本保持苹果-
21组 上上周比萝卜型略低，上周仅基本维持，本周依然在萝卜型左右
22组 上上周萝卜+，上周比萝卜+稍高，本周提升到苹果-
""".strip()

_DOCS_DIR = os.path.join(_BACKEND_ROOT, "..", "docs")
_MD_2025 = os.path.join(_DOCS_DIR, "去年2025个人课设报告批改各主题大致情况.md")
_MD_2026_REQ = os.path.join(_DOCS_DIR, "今年2026小组个人课设报告批改要求.md")
_DIR_2025_SRC = os.path.join(_DOCS_DIR, "去年2025课设报告批改结果")

_WEEK_RE = re.compile(r"W(\d+)", re.I)

_STEP1_WEEK_SCOPE = (
    "须基于本子内**全部周次**素材（从课设实验首张梯子图起至学期末收尾周），"
    "按周次推进串联分析，而非仅最近一两周。"
    "（当前批改在期末考试之后，以下周次指素材中的历史周次。）"
)


def _user_raw_dir(username: str = NOTEBOOK_USERNAME) -> str:
    return os.path.normpath(f"./received_dir/user_raw_file/{username.replace(chr(92), '/')}")


def _title_a(theme: str, gid: int) -> str:
    return f"S5素材A:{theme}G{gid:02d}组梯子图周次迭代梳理"


def _title_b3(theme: str, gid: int) -> str:
    return f"S5素材B3:{theme}G{gid:02d}组激励谈话牵引梳理"


def _title_b5(theme: str, gid: int) -> str:
    return f"S5素材B5:{theme}G{gid:02d}组规划代码8XML推进梳理"


def _title_s5_prior(theme: str, gid: int) -> str:
    return f"S5素材C:{theme}G{gid:02d}组前序综合批改梳理"


def _title_final(theme: str, gid: int) -> str:
    return f"S5:NK2026{theme}G{gid:02d}组个人课设报告综合批改"


def _report_pdf_name(theme: str, gid: int) -> str:
    return f"NK2026{theme}G{gid}组个人课设报告拼接汇总.pdf"


def _resolve_report_pdf_filename(
    theme: str, gid: int, username: str = NOTEBOOK_USERNAME
) -> Optional[str]:
    """在 user_raw_dir 解析拼接 PDF 实际文件名（兼容 G2 / G02）。"""
    d = _user_raw_dir(username)
    candidates = [
        _report_pdf_name(theme, gid),
        f"NK2026{theme}G{gid:02d}组个人课设报告拼接汇总.pdf",
    ]
    for name in candidates:
        if os.path.isfile(os.path.join(d, name)):
            return name
    keys = (f"{theme}G{gid}", f"{theme}G{gid:02d}")
    for fn in list_notebook_files(username):
        low = fn.lower()
        if "个人课设报告拼接汇总" not in fn or not low.endswith(".pdf"):
            continue
        if any(k in fn for k in keys):
            return fn
    return None


def _read_pdf_from_doc_cache(username: str, fn: str) -> str:
    """从 document_split_cache 读取 PDF 分割正文（与梯子图同源缓存）。"""
    from llm_langchain.document_cache import doc_cache

    file_path = os.path.join(_user_raw_dir(username), fn)
    if not os.path.isfile(file_path):
        return ""
    split_docs = doc_cache.load_split_docs(username, fn, file_path)
    if not split_docs:
        return ""
    return "\n".join(
        (getattr(s, "page_content", "") or "").strip() for s in split_docs
    ).strip()


# ---------------------------------------------------------------------------
# 日志与任务登记
# ---------------------------------------------------------------------------


@dataclass
class TaskRecord:
    step: str
    substep: str
    target: str = ""
    ok: bool = False
    model: str = ""
    chars_in: int = 0
    chars_out: int = 0
    detail: str = ""
    card_cid: Optional[int] = None


class RunLogger:
    def __init__(self, username: str = NOTEBOOK_USERNAME):
        self.username = username
        self.records: List[TaskRecord] = []
        log_dir = os.path.join(_user_raw_dir(username), "_nk2026_final_grading")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_path = os.path.join(log_dir, f"run_{ts}.log")
        self.registry_path = os.path.join(log_dir, "card_registry.json")
        self.registry: Dict[str, Any] = self._load_registry()

    def _load_registry(self) -> Dict[str, Any]:
        if os.path.isfile(self.registry_path):
            try:
                with open(self.registry_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"cards": {}, "updated_at": ""}

    def save_registry(self) -> None:
        with _LOG_LOCK:
            self.registry["updated_at"] = datetime.now().isoformat(timespec="seconds")
            with open(self.registry_path, "w", encoding="utf-8") as f:
                json.dump(self.registry, f, ensure_ascii=False, indent=2)

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        with _LOG_LOCK:
            print(line, flush=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    def add(self, rec: TaskRecord) -> None:
        with _LOG_LOCK:
            self.records.append(rec)
        status = "OK" if rec.ok else "FAIL"
        self.log(
            f"{status} | {rec.step}/{rec.substep} | {rec.target} | model={rec.model} "
            f"in={rec.chars_in} out={rec.chars_out} | {rec.detail[:120]}"
        )

    def print_summary_table(self) -> None:
        self.log("\n========== 任务完成情况汇总 ==========")
        hdr = f"{'步骤':<12} {'子步':<22} {'目标':<28} {'成功':<6} {'模型':<28} {'输出字数':<8}"
        self.log(hdr)
        self.log("-" * len(hdr))
        for r in self.records:
            self.log(
                f"{r.step:<12} {r.substep:<22} {r.target[:28]:<28} "
                f"{'是' if r.ok else '否':<6} {r.model[:28]:<28} {r.chars_out:<8}"
            )
        ok_n = sum(1 for r in self.records if r.ok)
        self.log(f"合计 {len(self.records)} 项，成功 {ok_n}，失败 {len(self.records) - ok_n}")
        self.log(f"日志文件: {self.log_path}")
        self.log(f"卡片注册表: {self.registry_path}")


# ---------------------------------------------------------------------------
# LLM 调用（opus 仅 model/messages/max_tokens）
# ---------------------------------------------------------------------------


def _cloudapi_cfg() -> Dict[str, str]:
    """与窗口选 claude-opus-4.8 一致：从 model_config 读取真实 model_name（claude-opus-4-8）。"""
    from app_chat.scene_models import resolve_openai_cfg_from_abbr

    cfg = resolve_openai_cfg_from_abbr(
        "claude-opus-4.8",
        default_model="claude-opus-4-8",
        default_base="https://chat.cloudapi.vip/v1/",
        default_key=os.environ.get(
            "NKCN_CLOUDAPI_KEY",
            os.environ.get("NKCN_LLM_API_KEY", ""),
        ),
    )
    return cfg


def _dmxapi_cfg() -> Dict[str, str]:
    return {
        "model": os.environ.get("NKCN_DMT_GEMINI_MODEL", "gemini-3.1-pro-preview"),
        "base_url": os.environ.get("NKCN_DMT_GEMINI_BASE_URL", "https://www.dmxapi.cn/v1").rstrip("/"),
        "api_key": os.environ.get(
            "NKCN_DMT_GEMINI_API_KEY",
            os.environ.get("DMX_API_KEY", ""),
        ),
    }


def _deepseek_cfg() -> Dict[str, str]:
    return {
        "model": os.environ.get("NKCN_DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "base_url": "https://api.deepseek.com",
        "api_key": os.environ.get(
            "DEEPSEEK_API_KEY",
            os.environ.get("DEEPSEEK_API_KEY", ""),
        ),
    }


def _call_opus(messages: List[Dict[str, str]], max_tokens: int = 8192) -> str:
    cfg = _cloudapi_cfg()
    client = OpenAI(
        api_key=cfg["api_key"],
        base_url=cfg["base_url"].rstrip("/") + "/",
        timeout=600.0,
        default_headers={"x-foo": "true"},
        max_retries=0,  # 由 llm_generate 统一重试/回退，避免 SDK 与脚本双重重试
    )
    rsp = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        max_tokens=max_tokens,
    )
    return str(rsp.choices[0].message.content or "").strip()


def _call_openai_compat(cfg: Dict[str, str], messages: List[Dict[str, str]], max_tokens: int) -> str:
    client = OpenAI(
        api_key=cfg["api_key"],
        base_url=str(cfg["base_url"]).rstrip("/") + "/",
        timeout=600.0,
    )
    rsp = client.chat.completions.create(
        model=cfg["model"],
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
    )
    return str(rsp.choices[0].message.content or "").strip()


def llm_generate(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int = 8192,
) -> Tuple[str, str]:
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    chain = [
        ("claude-opus-4.8", _call_opus, 2),
        ("gemini-3.1-pro-preview", lambda m, t: _call_openai_compat(_dmxapi_cfg(), m, t), 2),
        ("deepseek-v4-flash", lambda m, t: _call_openai_compat(_deepseek_cfg(), m, t), 2),
    ]
    last_err = ""
    for label, fn, tries in chain:
        for i in range(tries):
            try:
                text = fn(messages, max_tokens)
                if text:
                    return text, f"{label} 第{i + 1}次"
                last_err = "empty_output"
            except Exception as e:
                last_err = str(e)
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(last_err or "all_models_failed")


# ---------------------------------------------------------------------------
# 素材读取
# ---------------------------------------------------------------------------


def _cap_text(text: str, cap: Optional[int], label: str = "") -> str:
    t = (text or "").strip()
    if cap is None or len(t) <= cap:
        return t
    return t[:cap] + f"\n…（{label}截断，原长{len(t)}字）"


def _sample_text_evenly(text: str, max_len: int) -> str:
    """均匀抽样（首/中/尾），避免只保留后半段。"""
    t = (text or "").strip()
    if max_len <= 0:
        return ""
    if len(t) <= max_len:
        return t
    seg = max(max_len // 3, 1)
    mid_start = max(0, (len(t) - seg) // 2)
    parts = [t[:seg], t[mid_start: mid_start + seg], t[-seg:]]
    out = "\n…（均匀抽样）…\n".join(p for p in parts if p)
    return out[:max_len]


_NOTEBOOK_VECTOR_READY = False
LOAD_USER_WAIT_TIMEOUT = 180
LOAD_USER_POLL_INTERVAL = 2


def _chroma_sqlite_files_for_user(username: str) -> List[str]:
    """本子 Chroma 持久化 sqlite 路径（主库 + 混合从库），去重保序。"""
    from llm_langchain import parse_input

    actual_db_path, _, secondary_db_path = parse_input.get_user_db_path(username)
    out: List[str] = []
    for path in (actual_db_path, secondary_db_path):
        if not path:
            continue
        db_file = os.path.join(path, "chroma.sqlite3")
        if os.path.isfile(db_file) and db_file not in out:
            out.append(db_file)
    return out


def _chroma_image_docs_readonly_sqlite(
    db_file: str,
    collection_name: str,
    source_path: str,
) -> List[Tuple[int, str]]:
    """
    只读 sqlite 拉取某文件的全部图片理解块（不经过 Chroma API，避免 readonly 库写锁失败）。
    返回 [(seq, page_content), ...]，seq 为 1-based。
    """
    import sqlite3

    uri = f"file:{db_file}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=8.0)
    rows: List[Tuple[int, str]] = []
    try:
        conn.execute("PRAGMA query_only = ON;")
        conn.execute("PRAGMA busy_timeout = 5000;")

        coll_row = conn.execute(
            "SELECT id FROM collections WHERE name = ? LIMIT 1;",
            (collection_name,),
        ).fetchone()
        if not coll_row:
            return []
        collection_id = coll_row[0]

        candidate_sqls = [
            # 新 schema：embeddings.segment_id -> segments.collection_id
            """
            SELECT e.id
            FROM embeddings e
            JOIN segments s ON e.segment_id = s.id
            JOIN embedding_metadata ms ON ms.id = e.id AND ms.key = 'source' AND ms.string_value = ?
            WHERE s.collection_id = ?
            """,
            # 无 segments 约束
            """
            SELECT e.id
            FROM embeddings e
            JOIN embedding_metadata ms ON ms.id = e.id AND ms.key = 'source' AND ms.string_value = ?
            """,
        ]
        embedding_ids: List[int] = []
        for sql in candidate_sqls:
            try:
                params = (source_path, collection_id) if "collection_id" in sql else (source_path,)
                embedding_ids = [r[0] for r in conn.execute(sql, params).fetchall()]
                if embedding_ids:
                    break
            except Exception:
                continue
        if not embedding_ids:
            return []

        for eid in embedding_ids:
            meta_rows = conn.execute(
                "SELECT key, string_value, int_value FROM embedding_metadata WHERE id = ?;",
                (eid,),
            ).fetchall()
            meta = {k: (sv if sv is not None else iv) for k, sv, iv in meta_rows}
            doc_type = meta.get("type")
            if doc_type not in (None, "", "image"):
                continue
            seq_raw = meta.get("seq")
            try:
                seq = int(seq_raw) if seq_raw is not None else 0
            except (TypeError, ValueError):
                continue
            doc = meta.get("chroma:document") or meta.get("document") or ""
            doc = (doc or "").strip()
            if not doc or seq <= 0:
                continue
            rows.append((seq, doc))
    except Exception as e:
        print(f"[nk2026] 只读 sqlite 拉取图片理解失败 {db_file}: {e}")
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    rows.sort(key=lambda x: x[0])
    return rows


def _ladder_three_layer_from_chroma_sqlite_readonly(username: str, doc_name: str) -> str:
    """从 Chroma sqlite 只读读取梯子图三层理解（与网页 get_pdf_image_sum 同源数据）。"""
    from llm_langchain import util

    source_path = util.construct_file_path(username, doc_name)
    collection_name = util.construct_collection(username)
    parts: List[str] = []
    seen_seq: set = set()
    for db_file in _chroma_sqlite_files_for_user(username):
        for seq, doc in _chroma_image_docs_readonly_sqlite(db_file, collection_name, source_path):
            if seq in seen_seq:
                continue
            seen_seq.add(seq)
            parts.append(f"【{doc_name} 第{seq}页/张·三层理解文本·sqlite只读】\n{doc}")
    return "\n\n".join(parts)


def _ensure_notebook_vector_store(logger: RunLogger, username: str = NOTEBOOK_USERNAME) -> bool:
    """
    独立脚本未走前端 load_user 时，global_var.store_memory 为空，
    get_pdf_image_sum 会 KeyError。此处仅挂载 Chroma 向量库（不遍历全本子分割）。
    返回是否成功；Chroma 打开需写权限，失败时调用方应走 document_split_cache / sqlite 只读。
    """
    global _NOTEBOOK_VECTOR_READY
    from threading import RLock
    from langchain_community.vectorstores import Chroma
    from llm_langchain import global_var, parse_input, util

    if (
        _NOTEBOOK_VECTOR_READY
        and username in global_var.store_memory
        and global_var.store_memory[username].get("vector_store")
    ):
        return True

    if username in global_var.store_memory and global_var.store_memory[username].get("vector_store"):
        _NOTEBOOK_VECTOR_READY = True
        return True

    if username not in parse_input.lock:
        parse_input.lock[username] = RLock()

    actual_db_path, db_type, secondary_db_path = parse_input.get_user_db_path(username)
    collection_name = util.construct_collection(username)
    logger.log(f"加载本子向量库 ({db_type}) path={actual_db_path}")

    try:
        vector_store = Chroma(
            collection_name=collection_name,
            embedding_function=parse_input.embeddings,
            persist_directory=actual_db_path,
        )
    except Exception as e:
        logger.log(
            f"Chroma 挂载失败（常见原因：向量库目录只读或 Django 正占用锁）: {e}；"
            "将改用 document_split_cache / sqlite 只读"
        )
        return False

    global_var.store_memory.setdefault(username, {})["vector_store"] = vector_store

    if db_type == "混合" and secondary_db_path:
        try:
            global_var.store_memory[username]["secondary_vector_store"] = Chroma(
                collection_name=collection_name,
                embedding_function=parse_input.embeddings,
                persist_directory=secondary_db_path,
            )
        except Exception as e:
            logger.log(f"本子从库加载失败（继续用主库）: {e}")

    _NOTEBOOK_VECTOR_READY = True
    logger.log("本子向量库加载完成")
    return True


def _ensure_notebook_loaded(logger: RunLogger, username: str = NOTEBOOK_USERNAME) -> None:
    """完整 load_user（较慢），供向量库仍无数据时回退。"""
    from llm_langchain import global_var, parse_input

    if (
        username in global_var.store_memory
        and global_var.store_memory[username].get("vector_store")
        and (global_var.store_memory[username].get("split_file") or [])
    ):
        return

    logger.log(f"触发本子完整 load_user（{username}），可能需数分钟…")
    parse_input.load_user(username)
    deadline = time.time() + LOAD_USER_WAIT_TIMEOUT
    while time.time() < deadline:
        if (
            username in global_var.store_memory
            and global_var.store_memory[username].get("vector_store")
            and (global_var.store_memory[username].get("split_file") or [])
        ):
            logger.log("本子 load_user 完成")
            return
        time.sleep(LOAD_USER_POLL_INTERVAL)
    raise RuntimeError(f"等待本子 {username} 加载超时（{LOAD_USER_WAIT_TIMEOUT}s）")


def _ladder_three_layer_from_doc_cache(username: str, doc_name: str) -> str:
    """从 document_split_cache 读取图片三层理解文本（不向模型传图）。"""
    from llm_langchain.document_cache import doc_cache

    file_path = os.path.join(_user_raw_dir(username), doc_name)
    if not os.path.isfile(file_path):
        return ""
    split_docs = doc_cache.load_split_docs(username, doc_name, file_path)
    if not split_docs:
        return ""
    blocks: List[str] = []
    for doc in split_docs:
        meta = getattr(doc, "metadata", None) or {}
        if meta.get("type") != "image":
            continue
        content = (getattr(doc, "page_content", "") or "").strip()
        if not content:
            continue
        seq = meta.get("seq", "?")
        blocks.append(f"【{doc_name} 第{seq}张·三层理解文本·缓存】\n{content}")
    return "\n\n".join(blocks)


def _ladder_three_layer_text(username: str, doc_name: str, logger: Optional[RunLogger] = None) -> str:
    """
    梯子图三层理解：缓存 → sqlite 只读 → 内存向量库，不向模型传图。
    网页端能看图片理解，是因为 Django 已 load_user；独立脚本默认走只读路径，避免 Chroma 写锁。
    """
    cached = _ladder_three_layer_from_doc_cache(username, doc_name)
    if cached.strip():
        return cached

    sqlite_text = _ladder_three_layer_from_chroma_sqlite_readonly(username, doc_name)
    if sqlite_text.strip():
        return sqlite_text

    from llm_langchain import global_var, parse_input

    if not global_var.store_memory.get(username, {}).get("vector_store"):
        if logger:
            _ensure_notebook_vector_store(logger, username)

    parts: List[str] = []
    for seq in range(256):
        try:
            chunk = parse_input.get_pdf_image_sum(username, doc_name, seq)
        except Exception:
            break
        chunk = (chunk or "").strip()
        if not chunk or "图片分析结果暂未可用" in chunk or "未能获取到第" in chunk:
            if seq == 0:
                continue
            break
        parts.append(f"【{doc_name} 第{seq + 1}页/张·三层理解文本】\n{chunk}")
    return "\n\n".join(parts)


def _probe_ladder_text_ready(logger: RunLogger, names: Sequence[str]) -> None:
    """探测梯子图三层理解是否可读；仅在全失败时再尝试完整 load_user。"""
    probe_files = collect_ladder_a_files(names, "车联", 2)
    if not probe_files:
        return
    probe = _ladder_three_layer_text(NOTEBOOK_USERNAME, probe_files[0], logger=logger)
    if probe.strip():
        logger.log(f"梯子图三层理解可用（探测文件: {probe_files[0]}，{len(probe)} 字）")
        return
    logger.log("缓存/sqlite/向量库均未命中梯子图三层理解，尝试完整 load_user…")
    _ensure_notebook_loaded(logger)


def list_notebook_files(username: str = NOTEBOOK_USERNAME) -> List[str]:
    d = _user_raw_dir(username)
    if not os.path.isdir(d):
        return []
    out = []
    for fn in os.listdir(d):
        p = os.path.join(d, fn)
        if os.path.isfile(p):
            out.append(fn)
    return sorted(out)


def _read_doc_fulltext(username: str, fn: str, cap: Optional[int] = None) -> str:
    path = os.path.join(_user_raw_dir(username), fn)
    if not os.path.isfile(path):
        return ""
    ext = os.path.splitext(fn)[1].lower()
    if ext == ".pdf":
        try:
            import fitz

            doc = fitz.open(path)
            parts = []
            max_pages = 320 if "拼接汇总" in fn else 80
            for i in range(min(doc.page_count, max_pages)):
                parts.append(doc.load_page(i).get_text("text") or "")
            doc.close()
            return _cap_text("\n".join(parts), cap, fn)
        except Exception as e:
            return f"[PDF读取失败 {fn}: {e}]"
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return _cap_text(f.read(), cap, fn)
    except Exception as e:
        return f"[读取失败 {fn}: {e}]"


def _read_pdf_full_via_split(username: str, fn: str, cap: Optional[int] = None) -> str:
    """
    读取 PDF 全文：分割缓存/向量库 → fitz 直读 → document_split_cache。
    独立脚本未 load_user 时 get_split_by_user_docs 常返回空列表，必须回退直读文件。
    """
    from llm_langchain import parse_input

    text = ""
    try:
        segs = parse_input.get_split_by_user_docs(username, [fn])
        text = "\n".join(
            (getattr(s, "page_content", "") or "").strip() for s in (segs or [])
        ).strip()
    except Exception:
        text = ""

    if not text:
        text = (_read_doc_fulltext(username, fn, cap=None) or "").strip()
        if text.startswith("[PDF读取失败") or text.startswith("[读取失败"):
            text = ""

    if not text:
        text = _read_pdf_from_doc_cache(username, fn)

    if not text:
        return ""

    return _cap_text(text, cap, fn)


def collect_ladder_a_files(names: Sequence[str], theme: str, gid: int) -> List[str]:
    out: List[str] = []
    for fn in names:
        if "梯子图填写" not in fn:
            continue
        if theme not in fn:
            continue
        if not nk2026_matches_group(fn, gid):
            continue
        if "上半部分" not in fn and "下半部分" not in fn:
            continue
        out.append(fn)
    return sorted(out, key=lambda x: (week_num_from_filename(x) or 0, x))


def bundle_ladder_a(
    username: str,
    theme: str,
    gid: int,
    names: Sequence[str],
    logger: Optional[RunLogger] = None,
) -> str:
    """A.1/A.2：本子内该组全部周次上/下半梯子图，三层理解文本完整拼接。"""
    files = collect_ladder_a_files(names, theme, gid)
    if not files:
        return ""
    blocks: List[str] = []
    for fn in files:
        if _is_ladder_fill_image_filename(fn) or fn.lower().endswith(".pdf"):
            chunk = _ladder_three_layer_text(username, fn, logger=logger)
        else:
            chunk = _read_doc_fulltext(username, fn, cap=None)
        if not chunk.strip():
            continue
        wk = week_num_from_filename(fn)
        blocks.append(f"### 文件：{fn}（W{wk if wk else '?'}）\n{chunk}")
    joined = "\n\n".join(blocks)
    logger_note = f"共{len(files)}个梯子图文件，有效{len(blocks)}个，{len(joined)}字"
    return _cap_text(joined, STEP1_MATERIAL_CAP, f"梯子图A类·{logger_note}")


def match_b1(fn: str) -> bool:
    return "智能纪要" in fn and "周教研" in fn and bool(_WEEK_RE.search(fn))


def match_b2(fn: str) -> bool:
    return (
        "精进种子三线放空设计定版" in fn
        and bool(_WEEK_RE.search(fn))
        and theme_keyword_in_text(fn) is not None
    )


def match_b4(fn: str) -> bool:
    return "课设实验课后TA助教小结" in fn and bool(_WEEK_RE.search(fn))


def match_b3(fn: str, theme: str, gid: int) -> bool:
    if not matches_incentive_talk_filename(fn):
        return False
    if theme not in fn:
        return False
    if not nk2026_matches_group(fn, gid):
        return False
    gg = incentive_group_from_filename(fn)
    return gg == gid and bool(_WEEK_RE.search(fn))


def collect_b5_files(names: Sequence[str], theme: str, gid: int) -> List[str]:
    return sorted(
        [fn for fn in names if nk2026_matches_b_planning_xml_log_gxx(fn, theme, gid)],
        key=lambda x: (max_week_markers_in_filename(x), x),
    )


def bundle_pre_summary_files(username: str, files: Sequence[str], cap: Optional[int] = STEP1_MATERIAL_CAP) -> str:
    blocks: List[str] = []
    for fn in sorted(files, key=lambda x: (week_num_from_filename(x) or 0, x)):
        pres = _read_pre_summary_for_doc(username, fn)
        if pres.strip():
            blocks.append(f"### {fn}\n{pres}")
    return _cap_text("\n\n".join(blocks), cap, "pre_summary")


def bundle_fulltext_files(username: str, files: Sequence[str], cap: Optional[int] = STEP1_MATERIAL_CAP) -> str:
    blocks: List[str] = []
    for fn in sorted(files, key=lambda x: (week_num_from_filename(x) or 0, x)):
        txt = _read_doc_fulltext(username, fn, cap=None)
        if txt.strip():
            blocks.append(f"### {fn}\n{txt}")
    return _cap_text("\n\n".join(blocks), cap, "全文")


def bundle_b5_pre_summary(username: str, theme: str, gid: int, names: Sequence[str]) -> str:
    files = collect_b5_files(names, theme, gid)
    return bundle_pre_summary_files(username, files, STEP1_MATERIAL_CAP)


def collect_s5_prior_cards(theme: str, gid: int) -> List[Card]:
    """批改要求 C 类：前序周次 S5 综合批改卡，排除本脚本产出的 S5素材/S5:NK2026 卡。"""
    pat = re.compile(rf"^S5:W\d+{re.escape(theme)}G0*{gid}(?:组)?", re.I)
    skip_prefixes = ("S5素材", "S5:NK2026")
    cards = Card.objects.filter(username=NOTEBOOK_USERNAME).order_by("datetime", "cid")
    out: List[Card] = []
    for c in cards:
        title = (c.contentTitle or "").strip()
        if any(title.startswith(p) for p in skip_prefixes):
            continue
        if pat.match(title):
            out.append(c)
    return sorted(out, key=lambda c: (c.contentTitle or ""))


def bundle_s5_prior_cards(theme: str, gid: int) -> str:
    cards = collect_s5_prior_cards(theme, gid)
    blocks = []
    for c in cards:
        blocks.append(f"### {c.contentTitle} (cid={c.cid})\n{c.content or ''}")
    return _cap_text("\n\n".join(blocks), STEP1_MATERIAL_CAP, "S5前序卡")


def _lecture_pre_summary_dir() -> str:
    return os.path.join(_user_raw_dir(LECTURE_USERNAME), "pre_summary")


def _lecture_pre_image_dir() -> str:
    return os.path.join(_user_raw_dir(LECTURE_USERNAME), "pre_image_summary")


def _read_md_dir(prefix: str, directory: str, suffix_marker: str = "") -> str:
    if not os.path.isdir(directory):
        return ""
    blocks: List[str] = []
    for fn in sorted(os.listdir(directory)):
        if not fn.startswith(prefix):
            continue
        if suffix_marker and suffix_marker not in fn:
            continue
        path = os.path.join(directory, fn)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                t = f.read().strip()
            if t:
                blocks.append(f"### {fn}\n{t}")
        except Exception as e:
            blocks.append(f"### {fn}\n[读取失败: {e}]")
    return "\n\n".join(blocks)


def bundle_lecture_embed_presummary() -> str:
    return _cap_text(
        _read_md_dir("NK2026春·embed-lecture", _lecture_pre_summary_dir()),
        120000,
        "授课Presummary",
    )


def bundle_lecture_embed_preimage() -> str:
    d = _lecture_pre_image_dir()
    if not os.path.isdir(d):
        return ""
    blocks: List[str] = []
    for fn in sorted(os.listdir(d)):
        if not fn.startswith("NK2026春·embed-lecture"):
            continue
        if "PreImageOrigin" in fn:
            continue
        if "PreImageSummary" not in fn:
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                t = f.read().strip()
            if t:
                blocks.append(f"### {fn}\n{t}")
        except Exception as e:
            blocks.append(f"### {fn}\n[读取失败: {e}]")
    return _cap_text("\n\n".join(blocks), 120000, "授课PreImageSummary")


def bundle_lecture_meeting_presummary() -> str:
    d = _lecture_pre_summary_dir()
    if not os.path.isdir(d):
        return ""
    blocks: List[str] = []
    for fn in sorted(os.listdir(d)):
        if not fn.startswith("智能纪要：") or "NK2026春本·嵌入式系统" not in fn:
            continue
        path = os.path.join(d, fn)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                t = f.read().strip()
            if t:
                blocks.append(f"### {fn}\n{t}")
        except Exception as e:
            blocks.append(f"### {fn}\n[读取失败: {e}]")
    return _cap_text("\n\n".join(blocks), 120000, "授课课堂纪要")


def rag_scene_base_docs(username: str, theme: str, gid: int, query_extra: str = "") -> str:
    from llm_langchain import util as lc_util

    q = f"{theme} G{gid:02d}组 个人课设报告 嵌入式课设 角色 公份 私份 除乘加 {query_extra}"
    blocks: List[str] = []
    for doc in C_SCENE_DOCS:
        try:
            segs = lc_util.get_docs_all_split(
                username, [doc], [3], text_for_search=q, core_keyword=f"{theme}课设"
            )
            parts: List[str] = []
            for doc_seg in segs or []:
                for seg in doc_seg or []:
                    pc = getattr(seg, "page_content", "") or ""
                    if pc.strip():
                        parts.append(pc.strip())
            if parts:
                blocks.append(f"### C类·{doc}（相关搜索）\n" + "\n\n".join(parts[:12]))
        except Exception as e:
            blocks.append(f"### C类·{doc}\n[检索失败: {e}]")
    return _cap_text("\n\n".join(blocks), 50000, "C类RAG")


# ---------------------------------------------------------------------------
# 卡片写入
# ---------------------------------------------------------------------------


def _extract_keywords_from_content(
    content: str,
    key_topics: Optional[List[str]] = None,
    *,
    notebook_description: str = '',
    username: str = '',
) -> str:
    """与 add_card_directly 一致：统一抽取 keyWords（admin 可切模型）。"""
    from app_chat.card_keyword_extract import extract_card_semantic_keywords

    return extract_card_semantic_keywords(
        content,
        key_topics=key_topics or [],
        notebook_description=notebook_description,
        username=username or None,
        with_candidates=True,
    )


def _score_card_fields(username: str, content: str) -> Tuple[float, str, str, float, str, str]:
    """与 automation / generate_permanent_card 一致：红蓝打分 + SFT 评测（同步，避免线程内 asyncio 冲突）。"""
    from app_chat.views import get_small_model_server_url
    from llm_langchain import red_bule_rate
    from llm_langchain.red_bule_rate import extract_color_SFT, extract_number_SFT, extract_reason_SFT

    def _get_score() -> Tuple[float, str, str]:
        try:
            score, color, reason = red_bule_rate.get_rate(username, content)
            if score >= 1.0 and color != "紫":
                color = "紫"
            return float(score), color, reason or ""
        except Exception:
            return 4.5, "紫", ""

    def _get_sft() -> Tuple[float, str, str]:
        try:
            text = (content or "").replace("\n", "\\n")
            server_url = get_small_model_server_url(username)
            cmd = (
                f'curl -X POST -H "Content-Type: application/json" '
                f'-d \'{{"username":"{username}","text":"{text}"}}\' '
                f"{server_url}/invoke_rate"
            )
            result = subprocess.run(
                cmd, shell=True, check=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, timeout=60,
            )
            data_str = (result.stdout or "").strip()
            if data_str.startswith('"') and data_str.endswith('"'):
                data_str = data_str[1:-1]
            data_str = data_str.replace('\\"', '"').replace("\\\\", "\\")
            robj = json.loads(data_str)
            decoded = robj.get("result", "")
            if decoded and decoded != "fail":
                score_sft = float(extract_number_SFT(decoded)) if extract_number_SFT(decoded) is not None else 4.5
                color_sft = extract_color_SFT(decoded) or "紫"
                reason_sft = extract_reason_SFT(decoded) or ""
                if score_sft >= 1.0 and color_sft != "紫":
                    color_sft = "紫"
                return score_sft, color_sft, reason_sft
        except Exception:
            pass
        return 4.5, "紫", ""

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_score = ex.submit(_get_score)
        f_sft = ex.submit(_get_sft)
        score_t = f_score.result()
        sft_t = f_sft.result()
    return score_t[0], score_t[1], score_t[2], sft_t[0], sft_t[1], sft_t[2]


def _apply_card_system_metadata(
    logger: RunLogger,
    card: Card,
    content: str,
    content_title: str,
    writer: str,
    scene_name: str = NK2026_SCENE_NAME,
) -> None:
    """
    按 NKCN 系统流程填充 keyWords / score,color,reason / scoreSFT,colorSFT,reasonSFT /
    four_color_type,dmt_level。contentTitle 保持调用方指定的固定值。
    """
    from app_chat.scene_context_helper import get_notebook_description, get_scene_summary
    from app_chat.views import generate_title_and_analyze_keywords_parallel

    body = (content or "").strip()
    key_words = _extract_keywords_from_content(body)
    try:
        generate_title_and_analyze_keywords_parallel(
            key_words, body, NOTEBOOK_USERNAME, writer, scene_name, None
        )
    except Exception as e:
        logger.log(f"关键词四色/DMT 分析失败（继续）: {e}")

    score, color, reason, score_sft, color_sft, reason_sft = _score_card_fields(
        NOTEBOOK_USERNAME, body
    )

    scene_summary_info, subscene_summary_info = get_scene_summary(scene_name, None)
    notebook_desc = get_notebook_description(NOTEBOOK_USERNAME, scene_name)
    final_scene_summary = subscene_summary_info or scene_summary_info

    all_cards_data = list(
        Card.objects.filter(username=NOTEBOOK_USERNAME).values(
            "cid", "content", "contentTitle", "is_neuron", "is_evolved",
            "selection_count", "postIndex", "four_color_type", "dmt_level",
        )
    )
    current_card_data = {
        "content": body,
        "contentTitle": content_title,
        "is_neuron": False,
        "is_evolved": False,
        "selection_count": 0,
        "cid": card.cid,
        "username": NOTEBOOK_USERNAME,
    }
    four_color, dmt_level, is_analyzed = analyze_card_with_new_standard(
        current_card_data,
        scene_name=scene_name,
        sub_scene_name=None,
        scene_summary=final_scene_summary,
        notebook_description=notebook_desc,
        all_cards_data=all_cards_data,
        total_cards_count=len(all_cards_data),
    )

    card.keyWords = key_words
    card.contentTitle = content_title
    card.score = score
    card.color = color
    card.reason = reason
    card.scoreSFT = score_sft
    card.colorSFT = color_sft
    card.reasonSFT = reason_sft
    card.four_color_type = four_color or card.four_color_type or "P"
    card.dmt_level = dmt_level or card.dmt_level or "M"
    card.is_analyzed_by_new_standard = is_analyzed
    card.save(
        update_fields=[
            "keyWords", "contentTitle", "score", "color", "reason",
            "scoreSFT", "colorSFT", "reasonSFT",
            "four_color_type", "dmt_level", "is_analyzed_by_new_standard",
        ]
    )
    logger.log(
        f"卡片元数据已生成 cid={card.cid} kw={key_words[:24]} "
        f"score={score}/{score_sft} {color}/{color_sft}"
    )


def upsert_card(
    logger: RunLogger,
    content_title: str,
    content: str,
    *,
    post_cids: Optional[List[int]] = None,
    require_dmt: bool = False,
    scene_name: str = NK2026_SCENE_NAME,
    skip_existing: bool = True,
    writer: str = REAL_NAME,
) -> Card:
    existing = Card.objects.filter(
        username=NOTEBOOK_USERNAME, contentTitle=content_title
    ).first()
    if existing and skip_existing:
        logger.log(f"卡片已存在，跳过写入: {content_title} cid={existing.cid}")
        logger.registry.setdefault("cards", {})[content_title] = existing.cid
        return existing

    post_index = json.dumps(post_cids or [], ensure_ascii=False)
    created = False
    if existing:
        existing.content = content
        existing.postIndex = post_index
        existing.writer = writer
        if require_dmt:
            existing.three_window_models = {
                "main": "claude-opus-4.8",
                "up": "claude-opus-4.8",
                "down": "claude-opus-4.8",
            }
        existing.save(
            update_fields=["content", "postIndex", "writer"]
            + (["three_window_models"] if require_dmt else [])
        )
        card = existing
    else:
        card = Card.objects.create(
            username=NOTEBOOK_USERNAME,
            model_id="1430",
            status="0",
            content=content,
            title="来自模型1430的问答",
            contentTitle=content_title,
            score=-2,
            color="紫",
            reason="",
            scoreSFT=-1,
            colorSFT="紫",
            reasonSFT="",
            keyWords="",
            postIndex=post_index,
            writer=writer,
            three_window_models={"main": "claude-opus-4.8", "up": "claude-opus-4.8", "down": "claude-opus-4.8"},
        )
        created = True

    try:
        _apply_card_system_metadata(
            logger, card, content, content_title, writer, scene_name=scene_name
        )
    except Exception as e:
        logger.log(f"卡片系统元数据生成失败 cid={card.cid}: {e}")
        traceback.print_exc()

    if require_dmt and not card.three_window_models:
        card.three_window_models = {
            "main": "claude-opus-4.8", "up": "claude-opus-4.8", "down": "claude-opus-4.8",
        }
        card.save(update_fields=["three_window_models"])

    if created:
        logger.log(f"新建卡片: {content_title} cid={card.cid}")
    else:
        logger.log(f"更新卡片: {content_title} cid={card.cid}")
    logger.registry.setdefault("cards", {})[content_title] = card.cid
    logger.save_registry()
    return card


def get_card_content_by_title(
    logger: RunLogger, content_title: str, fallback_md: str = ""
) -> Tuple[str, Optional[int]]:
    cid = logger.registry.get("cards", {}).get(content_title)
    card = None
    if cid:
        card = Card.objects.filter(username=NOTEBOOK_USERNAME, cid=cid).first()
        if card and (card.contentTitle or "") != content_title:
            logger.log(f"cid 与 contentTitle 不一致，改按标题查找: {content_title}")
            card = None
    if not card:
        card = Card.objects.filter(
            username=NOTEBOOK_USERNAME, contentTitle=content_title
        ).first()
    if card:
        return card.content or "", card.cid
    if fallback_md and os.path.isfile(fallback_md):
        with open(fallback_md, "r", encoding="utf-8") as f:
            return f.read(), None
    return "", None


# ---------------------------------------------------------------------------
# 第①步
# ---------------------------------------------------------------------------

_SYSTEM_ANALYST = (
    "你是 NK2026 嵌入式课设综合批改教研专家。"
    "只输出正文，不要代码块包裹，不要多余开场白。"
)


def _user_with_limit(task: str, material: str, word_min: int, word_max: int) -> str:
    return (
        f"{task}\n\n"
        f"【硬性篇幅】全文控制在 {word_min}～{word_max} 汉字（含标点），不得超过 {word_max} 字。\n\n"
        f"【素材】\n{material}"
    )


def step1_a_ladder(logger: RunLogger, names: Sequence[str], theme: str, gid: int, skip_existing: bool) -> None:
    sub = "A梯子图"
    target = f"{theme}G{gid:02d}"
    title = _title_a(theme, gid)
    try:
        files = collect_ladder_a_files(names, theme, gid)
        if not files:
            logger.add(TaskRecord("1", sub, target, False, detail="本子内无匹配的梯子图文件名"))
            return
        material = bundle_ladder_a(NOTEBOOK_USERNAME, theme, gid, names, logger=logger)
        if not material.strip():
            logger.add(
                TaskRecord(
                    "1", sub, target, False,
                    detail=f"匹配{len(files)}个梯子图文件但三层理解文本均为空（检查向量库/缓存）",
                )
            )
            return
        task = (
            f"请分析并梳理 {theme} G{gid:02d} 组梯子图填写内容："
            f"{_STEP1_WEEK_SCOPE} "
            "串联各周迭代变化、与五角色公份/私份心得的关联；"
            "指出关键转折周次与可能原因。面向期末个人课设报告批改提供证据链。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, title, text, skip_existing=skip_existing)
        logger.add(
            TaskRecord(
                "1", sub, target, True, model, len(user), len(text),
                card_cid=card.cid,
            )
        )
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))
        traceback.print_exc()


def step1_b1(logger: RunLogger, names: Sequence[str], skip_existing: bool) -> None:
    sub, target = "B1周教研", "全局"
    try:
        files = [fn for fn in names if match_b1(fn)]
        logger.log(f"B1周教研：本子内匹配 {len(files)} 个文件，将全部纳入分析")
        material = bundle_pre_summary_files(NOTEBOOK_USERNAME, files)
        if not material.strip():
            logger.add(TaskRecord("1", sub, target, False, detail="无B1素材"))
            return
        task = (
            "分析「智能纪要：周教研」系列文档："
            f"{_STEP1_WEEK_SCOPE} "
            "助教在周次推进中需侧重关注点的变化、"
            "Wn 与 Vx.x 大版本阶段的认知提升与反思点。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, TITLE_B1, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(user), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))


def step1_b2(logger: RunLogger, names: Sequence[str], skip_existing: bool) -> None:
    sub, target = "B2精进种子", "全局"
    try:
        files = [fn for fn in names if match_b2(fn)]
        logger.log(f"B2精进种子：本子内匹配 {len(files)} 个文件，将全部纳入分析")
        material = bundle_pre_summary_files(NOTEBOOK_USERNAME, files)
        if not material.strip():
            logger.add(TaskRecord("1", sub, target, False, detail="无B2素材"))
            return
        task = (
            "分析助教「精进种子三线放空设计定版」："
            f"{_STEP1_WEEK_SCOPE} "
            "在各周次、Vx.x 版本中的优缺点、"
            "僵化风险、周次间承上启下是否到位。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, TITLE_B2, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(user), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))


def step1_b4(logger: RunLogger, names: Sequence[str], skip_existing: bool) -> None:
    sub, target = "B4TA小结", "全局"
    try:
        files = [fn for fn in names if match_b4(fn)]
        logger.log(f"B4TA小结：本子内匹配 {len(files)} 个文件，将全部纳入分析")
        material = bundle_fulltext_files(NOTEBOOK_USERNAME, files)
        if not material.strip():
            logger.add(TaskRecord("1", sub, target, False, detail="无B4素材"))
            return
        task = (
            "分析每周「课设实验课后TA助教小结」："
            f"{_STEP1_WEEK_SCOPE} "
            "优秀涌现与暴露问题在各周次、Vx.x 中的变化；"
            "哪些持续存在、哪些新出现；标出关键时间节点与可能诱因。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, TITLE_B4, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(user), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))


def step1_b3(logger: RunLogger, names: Sequence[str], theme: str, gid: int, skip_existing: bool) -> None:
    sub = "B3激励谈话"
    target = f"{theme}G{gid:02d}"
    title = _title_b3(theme, gid)
    try:
        files = [fn for fn in names if match_b3(fn, theme, gid)]
        if not files:
            logger.add(TaskRecord("1", sub, target, True, detail="该组无B3素材，正常跳过"))
            return
        material = bundle_fulltext_files(NOTEBOOK_USERNAME, files)
        task = (
            f"分析 {theme} G{gid:02d} 组在各周次、大版本递进中与教师/助教的激励谈话实录："
            f"{_STEP1_WEEK_SCOPE} "
            "牵引侧重点变化、优缺点、关键时间节点与可能原因。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, title, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(user), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))


def step1_b5(logger: RunLogger, names: Sequence[str], theme: str, gid: int, skip_existing: bool) -> None:
    sub = "B5规划8XML"
    target = f"{theme}G{gid:02d}"
    title = _title_b5(theme, gid)
    try:
        material = bundle_b5_pre_summary(NOTEBOOK_USERNAME, theme, gid, names)
        if not material.strip():
            logger.add(TaskRecord("1", sub, target, False, detail="无B5素材"))
            return
        task = (
            f"分析 {theme} G{gid:02d} 组规划表、代码及注释修改、8XML 日志："
            f"{_STEP1_WEEK_SCOPE} "
            "在各周次、版本中的变化；"
            "亮点与弱点；规划推进感强弱、角色代码量比例、段注释与日志分层是否清晰；"
            "关键时间节点与可能原因。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, title, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(user), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))


def step1_s5_prior(logger: RunLogger, theme: str, gid: int, skip_existing: bool) -> None:
    sub = "C前序S5"
    target = f"{theme}G{gid:02d}"
    title = _title_s5_prior(theme, gid)
    try:
        material = bundle_s5_prior_cards(theme, gid)
        if not material.strip():
            logger.add(TaskRecord("1", sub, target, False, detail="无前序S5卡片"))
            return
        task = (
            f"基于前序 S5:Wn{theme}G{gid:02d}组 综合批改卡片，梳理该组："
            f"{_STEP1_WEEK_SCOPE} "
            "梯子图及周边批改态势：强中弱、稳定/振荡/积极进步等；单周与跨周亮点与问题；"
            "关键时间节点与可能原因。"
        )
        user = _user_with_limit(task, material, 500, 600)
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        card = upsert_card(logger, title, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(user), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))


def step1_lecture(logger: RunLogger, skip_existing: bool) -> None:
    sub = "E授课凝练"
    target = "全局"
    try:
        p1 = bundle_lecture_embed_presummary()
        p2 = bundle_lecture_embed_preimage()
        p3 = bundle_lecture_meeting_presummary()
        if not (p1.strip() or p2.strip() or p3.strip()):
            logger.add(TaskRecord("1", sub, target, False, detail="无授课素材"))
            return

        task1 = (
            "对下列 NK2026春 embed-lecture 的 Presummary 做浓缩、摘要，"
            "萃取普通知识（trad）/组织知识（org）/部落知识（trib）三类，"
            "并深刻理解这些授课内容与三主题课设的关联。"
        )
        u1 = _user_with_limit(task1, p1, 400, 800)
        t1, m1 = llm_generate(_SYSTEM_ANALYST, u1)
        logger.add(TaskRecord("1", sub + "-embed文字", target, True, m1, len(u1), len(t1)))

        task2 = (
            "对下列 NK2026春 embed-lecture 的 PreImageSummary（PPT识图摘要）做浓缩、摘要，"
            "萃取普通知识/组织知识/部落知识三类，并深刻理解这些授课内容与三主题课设的关联。"
        )
        u2 = _user_with_limit(task2, p2, 400, 800)
        t2, m2 = llm_generate(_SYSTEM_ANALYST, u2)
        logger.add(TaskRecord("1", sub + "-embed图", target, True, m2, len(u2), len(t2)))

        task3 = (
            "对下列课堂实录智能纪要做浓缩、摘要，萃取普通知识/组织知识/部落知识三类，"
            "并深刻理解授课（含课程专业知识与课设相关内容）与三主题课设的关联。"
        )
        u3 = _user_with_limit(task3, p3, 400, 800)
        t3, m3 = llm_generate(_SYSTEM_ANALYST, u3)
        logger.add(TaskRecord("1", sub + "-课堂纪要", target, True, m3, len(u3), len(t3)))

        merge_material = f"【embed文字摘要】\n{t1}\n\n【embed图摘要】\n{t2}\n\n【课堂纪要摘要】\n{t3}"
        task4 = (
            "将以上三次摘要进一步凝练为一篇总述（500～800字）："
            "深刻理解授课与三主题课设中的三类知识，以及课程授课与主题课设之间的关联；"
            "强调课设服务授课、实验只做本主题但报告宜有跨主题视野。"
        )
        u4 = _user_with_limit(task4, merge_material, 500, 800)
        text, model = llm_generate(_SYSTEM_ANALYST, u4)
        card = upsert_card(logger, TITLE_LECTURE, text, skip_existing=skip_existing)
        logger.add(TaskRecord("1", sub, target, True, model, len(u4), len(text), card_cid=card.cid))
    except Exception as e:
        logger.add(TaskRecord("1", sub, target, False, detail=str(e)))
        traceback.print_exc()


def run_step1(logger: RunLogger, skip_existing: bool = True) -> None:
    logger.log("========== 第①步：素材梳理卡片 ==========")
    names = list_notebook_files()
    logger.log(f"本子共 {len(names)} 个文件")

    # 全局 B1 B2 B4
    step1_b1(logger, names, skip_existing)
    step1_b2(logger, names, skip_existing)
    step1_b4(logger, names, skip_existing)
    step1_lecture(logger, skip_existing)

    _probe_ladder_text_ready(logger, names)

    def _group_job(theme: str, gid: int) -> None:
        step1_a_ladder(logger, names, theme, gid, skip_existing)
        step1_b3(logger, names, theme, gid, skip_existing)
        step1_b5(logger, names, theme, gid, skip_existing)
        step1_s5_prior(logger, theme, gid, skip_existing)

    pairs = [(t, g) for t, gs in THEME_GROUPS.items() for g in gs]
    with ThreadPoolExecutor(max_workers=MAX_GROUP_CONCURRENT) as ex:
        futs = {ex.submit(_group_job, t, g): (t, g) for t, g in pairs}
        for fut in as_completed(futs):
            t, g = futs[fut]
            try:
                fut.result()
            except Exception as e:
                logger.log(f"组任务异常 {t}G{g:02d}: {e}")


def run_step1_only_a(logger: RunLogger, skip_existing: bool = True) -> None:
    """仅补 20 张 A 梯子图梳理卡，不运行 B1～B5/C/E 等其它子步。"""
    logger.log("========== 第①步（仅A梯子图）：补 20 组 ==========")
    names = list_notebook_files()
    logger.log(f"本子共 {len(names)} 个文件")

    _probe_ladder_text_ready(logger, names)

    pairs = [(t, g) for t, gs in THEME_GROUPS.items() for g in gs]

    def _job(theme: str, gid: int) -> None:
        step1_a_ladder(logger, names, theme, gid, skip_existing)

    with ThreadPoolExecutor(max_workers=MAX_GROUP_CONCURRENT) as ex:
        futs = {ex.submit(_job, t, g): (t, g) for t, g in pairs}
        for fut in as_completed(futs):
            t, g = futs[fut]
            try:
                fut.result()
            except Exception as e:
                logger.log(f"仅A组任务异常 {t}G{g:02d}: {e}")


# ---------------------------------------------------------------------------
# 第③步：最终批改
# ---------------------------------------------------------------------------


def _collect_input_cards_for_group(
    logger: RunLogger, theme: str, gid: int
) -> Tuple[List[Tuple[str, str, Optional[int]]], List[int]]:
    """返回 [(标题, 正文, cid), ...] 与 postIndex cid 列表。

    卡片字母对应批改要求：A, B1～B5, C, D(2025), E(授课/S5素材E:), F(2026要求)。
    G 类为场景预置文档 RAG，在第③步单独注入，不在此列表。
    """
    titles = [
        _title_a(theme, gid),       # A
        TITLE_B1,                   # B1
        TITLE_B2,                   # B2
        TITLE_B4,                   # B4
        _title_b3(theme, gid),      # B3
        _title_b5(theme, gid),      # B5
        _title_s5_prior(theme, gid),  # C
        TITLE_2025,                 # D
        TITLE_LECTURE,              # E
        TITLE_2026_REQ,             # F
    ]
    fallbacks = {
        TITLE_2025: _MD_2025,
        TITLE_2026_REQ: _MD_2026_REQ,
    }
    blocks: List[Tuple[str, str, Optional[int]]] = []
    cids: List[int] = []
    for title in titles:
        fb = fallbacks.get(title, "")
        body, cid = get_card_content_by_title(logger, title, fb)
        if not body.strip():
            if title == _title_b3(theme, gid):
                logger.log(f"可选卡片缺失（正常）: {title}")
                continue
            logger.log(f"警告：缺少输入卡片 {title}")
            continue
        blocks.append((title, body, cid))
        if cid:
            cids.append(cid)
    return blocks, cids


def _step3_cap_sequence() -> List[int]:
    caps = [STEP3_INPUT_CAP]
    for delta in STEP3_CAP_REDUCE_DELTAS:
        caps.append(caps[-1] - delta)
    return caps


def _join_step3_material(
    req_body: str,
    cards_blob: str,
    pdf_name: str,
    pdf_text: str,
    c_rag: str,
) -> str:
    return (
        f"【批改要求】\n{req_body}\n\n"
        f"【素材卡片·A/B/C/D/E】\n{cards_blob}\n\n"
        f"【主材料·个人课设报告拼接PDF·{pdf_name}】\n{pdf_text}\n\n"
        f"【G类·场景预置文档相关搜索片段】\n{c_rag}"
    )


def _fit_step3_material_normal(material: str, cap: int) -> str:
    """正常路径：完整注入，仅当总长超 cap 时截断。"""
    if len(material) <= cap:
        return material
    return _cap_text(material, cap, "step3输入")


def _fit_step3_material_degraded(
    req_body: str,
    card_blocks: List[Tuple[str, str, Optional[int]]],
    pdf_name: str,
    pdf_text: str,
    c_rag: str,
    cap: int,
) -> str:
    """多次报错后的降级：PDF 尽量全文，每张素材卡均匀抽样且必有内容。"""
    req_sec = f"【批改要求】\n{req_body}\n\n"
    overhead = (
        len(req_sec)
        + len("【素材卡片·A/B/C/D/E】\n")
        + len(f"【主材料·个人课设报告拼接PDF·{pdf_name}】\n")
        + len("【G类·场景预置文档相关搜索片段】\n")
        + 80
    )
    remaining = max(cap - overhead, 1200)
    n_slots = max(len(card_blocks), 1) + 2
    per_card = max(remaining // (n_slots + 2), 180)

    card_parts: List[str] = []
    for t, body, cid in card_blocks:
        sampled = _sample_text_evenly(body, per_card)
        card_parts.append(f"### 卡片：{t} (cid={cid})\n{sampled}")
    cards_blob = "\n\n".join(card_parts) if card_parts else "（无素材卡片）"

    used = len(req_sec) + len("【素材卡片·A/B/C/D/E】\n") + len(cards_blob) + 4
    left = max(cap - used, 600)
    pdf_budget = max(int(left * 0.72), 300)
    rag_budget = max(left - pdf_budget, 150)

    pdf_body = pdf_text if len(pdf_text) <= pdf_budget else _sample_text_evenly(pdf_text, pdf_budget)
    rag_body = _sample_text_evenly(c_rag, rag_budget) if (c_rag or "").strip() else ""

    material = _join_step3_material(req_body, cards_blob, pdf_name, pdf_body, rag_body)
    return material if len(material) <= cap else material[:cap]


def _group_score_prompt(gid: int) -> str:
    info = GROUP_SCORE_INFO.get(gid)
    if not info:
        return ""
    return (
        f"【本组整体组分参考】G{gid:02d}：{info['grade']}（百分制{info['percent']}，"
        f"5分制基准约{info['score5']}）。各角色评分以此为基础分合理上下浮动；"
        "基础分已较高，以持平或适度下调为主，除非该角色对全组有显著突出贡献可适当上浮。"
    )


def _step3_llm_generate(
    logger: RunLogger,
    task: str,
    req_body: str,
    card_blocks: List[Tuple[str, str, Optional[int]]],
    pdf_name: str,
    pdf_text: str,
    c_rag: str,
) -> Tuple[str, str, int]:
    cards_blob = "\n\n".join(
        f"### 卡片：{t} (cid={cid})\n{body}" for t, body, cid in card_blocks
    )
    full_material = _join_step3_material(req_body, cards_blob, pdf_name, pdf_text, c_rag)
    caps = _step3_cap_sequence()

    for i, cap in enumerate(caps):
        material = _fit_step3_material_normal(full_material, cap)
        user = task + "\n\n【材料】\n" + material
        try:
            text, model = llm_generate(_SYSTEM_ANALYST, user, max_tokens=16000)
            mode = "正常" if i == 0 and len(material) == len(full_material) else f"缩减cap={cap}"
            logger.log(f"step3 LLM成功 {mode} 输入{len(user)}字")
            return text, model, len(user)
        except Exception as e:
            logger.log(f"step3 LLM失败 cap={cap} ({len(user)}字): {e}")

    cap = caps[-1]
    material = _fit_step3_material_degraded(
        req_body, card_blocks, pdf_name, pdf_text, c_rag, cap
    )
    user = task + "\n\n【材料】\n" + material
    logger.log(f"step3 启用降级模式 cap={cap} 输入约{len(user)}字")
    text, model = llm_generate(_SYSTEM_ANALYST, user, max_tokens=16000)
    return text, model, len(user)


def step3_grade_group(
    logger: RunLogger, theme: str, gid: int, skip_existing: bool
) -> None:
    sub = "最终批改"
    target = f"{theme}G{gid:02d}"
    final_title = _title_final(theme, gid)
    try:
        card_blocks, post_cids = _collect_input_cards_for_group(logger, theme, gid)
        pdf_name = _resolve_report_pdf_filename(theme, gid)
        if not pdf_name:
            expect = _report_pdf_name(theme, gid)
            path = os.path.join(_user_raw_dir(NOTEBOOK_USERNAME), expect)
            raise RuntimeError(
                f"未找到拼接 PDF（期望 {expect} 或 G{gid:02d} 变体；"
                f"目录 {_user_raw_dir(NOTEBOOK_USERNAME)} 下无匹配文件；"
                f"直查路径存在={os.path.isfile(path)}）"
            )
        pdf_text = _read_pdf_full_via_split(NOTEBOOK_USERNAME, pdf_name)
        if not pdf_text.strip():
            path = os.path.join(_user_raw_dir(NOTEBOOK_USERNAME), pdf_name)
            raise RuntimeError(
                f"拼接 PDF 正文为空：{pdf_name}（文件存在={os.path.isfile(path)}；"
                "若为扫描件请先在系统内打开该 PDF 完成理解/分割入库）"
            )

        c_rag = rag_scene_base_docs(NOTEBOOK_USERNAME, theme, gid)
        role_line = nk2026_group_role_line(gid)
        req_body, _ = get_card_content_by_title(logger, TITLE_2026_REQ, _MD_2026_REQ)
        score_hint = _group_score_prompt(gid)

        task = (
            f"请为 {theme} G{gid:02d} 组生成「个人课设报告综合批改」全文。\n"
            f"角色顺序（按报告与角色行）：{role_line or '组长→需求员→周志员→优裁员→展示员（→组长助理若有）'}\n"
            "严格按《今年2026小组个人课设报告批改要求》输出每位角色一节，每人约550字（不超过600字）。\n"
            "须综合：主材料拼接 PDF、多类周边信息素材卡片 A/B1～B5/C/D/E、G 类场景预置文档相关片段。\n"
            "【重点】E 类卡片素材（授课与课设三类知识关联凝练卡）须深度融合："
            "课设本质服务授课；课设实验只做本主题，但报告宜了解另两主题；课堂授课有主题综合视角。\n"
            "D 类（去年2025三主题概况）须与今年各小组角色真实情况比对优缺。\n"
            "A/B/C 类也是重要的小组本学期多周各类材料情况分析，也须充分综合。\n"
            "总之，需按照今年2026小组个人课设报告批改要求，扎实做全、做好、做精。\n"
            f"{score_hint}\n"
            f"{GROUP_ARCHETYPE_W13_15}\n"
            "评价结构：理解描述、评价分析（知识问题/技能错误/能力缺陷/协作）、综合分、"
            "重叠度、批语和建议、认知提升与跨年继承、课程改进建议。\n"
            "打分与理由要求准；突出涌现、收获、反思与对明年课程/助教的继承性建议要求精。\n"
            "输出 Markdown，每人以 ## 角色：姓名 开头。"
        )
        text, model, user_len = _step3_llm_generate(
            logger, task, req_body, card_blocks, pdf_name, pdf_text, c_rag
        )
        card = upsert_card(
            logger,
            final_title,
            text,
            post_cids=post_cids,
            require_dmt=True,
            skip_existing=skip_existing,
            writer=THEME_STEP3_WRITERS.get(theme, REAL_NAME),
        )
        logger.add(
            TaskRecord(
                "3", sub, target, True, model, user_len, len(text), card_cid=card.cid
            )
        )
    except Exception as e:
        logger.add(TaskRecord("3", sub, target, False, detail=str(e)))
        traceback.print_exc()


def run_step3(logger: RunLogger, skip_existing: bool = True) -> None:
    logger.log("========== 第③步：20组最终综合批改 ==========")
    if not _ensure_notebook_vector_store(logger):
        logger.log("第③步 G 类 RAG 可能受影响；若检索失败请检查向量库目录写权限或先 stop Django 再跑")
    pairs = [(t, g) for t, gs in THEME_GROUPS.items() for g in gs]

    def _job(t: str, g: int) -> None:
        step3_grade_group(logger, t, g, skip_existing)

    with ThreadPoolExecutor(max_workers=MAX_GROUP_CONCURRENT) as ex:
        futs = {ex.submit(_job, t, g): (t, g) for t, g in pairs}
        for fut in as_completed(futs):
            t, g = futs[fut]
            try:
                fut.result()
            except Exception as e:
                logger.log(f"第③步组异常 {t}G{g:02d}: {e}")


def _cards_for_metadata_backfill() -> List[Card]:
    """仅第①步脚本写入的 S5素材* 卡（字段曾为写死值）。不含 D/F 手动卡、不含 S5:NK2026 最终卡。"""
    out: List[Card] = []
    for c in Card.objects.filter(username=NOTEBOOK_USERNAME).order_by("cid"):
        title = (c.contentTitle or "").strip()
        if title.startswith("S5素材"):
            out.append(c)
    return out


def run_backfill_metadata(logger: RunLogger) -> None:
    """不改正文与 contentTitle，仅补齐 keyWords / score / reason / scoreSFT 等系统字段。"""
    cards = _cards_for_metadata_backfill()
    logger.log(f"========== 元数据回填：共 {len(cards)} 张卡片 ==========")
    ok_n = 0
    for c in cards:
        title = (c.contentTitle or "").strip()
        body = (c.content or "").strip()
        if not body:
            logger.add(TaskRecord("meta", "回填", title[:28], False, detail="正文为空"))
            continue
        writer = (c.writer or REAL_NAME).strip() or REAL_NAME
        try:
            _apply_card_system_metadata(logger, c, body, title, writer)
            ok_n += 1
            logger.add(
                TaskRecord("meta", "回填", title[:28], True, detail=f"cid={c.cid}", card_cid=c.cid)
            )
        except Exception as e:
            logger.add(TaskRecord("meta", "回填", title[:28], False, detail=str(e)[:120]))
            traceback.print_exc()
    logger.log(f"元数据回填完成：成功 {ok_n}/{len(cards)}")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def run_step_prep(logger: RunLogger) -> None:
    """从 docs/去年2025课设报告批改结果 三主题文件生成/刷新 2025 概况 md（500～800字）。"""
    logger.log("========== 预备：生成去年2025概况 md ==========")
    src_files = []
    if os.path.isdir(_DIR_2025_SRC):
        for fn in sorted(os.listdir(_DIR_2025_SRC)):
            if fn.endswith(".md"):
                path = os.path.join(_DIR_2025_SRC, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        src_files.append(f"### {fn}\n{f.read()[:80000]}")
                except Exception as e:
                    logger.log(f"读取失败 {fn}: {e}")
    if not src_files:
        logger.log("未找到去年2025源素材，跳过 prep")
        return
    material = _cap_text("\n\n".join(src_files), 200000, "2025源")
    task = (
        "根据下列三主题（车联II、纸联III、体联IV）2025个人课设报告批改汇总素材，"
        "写一份「去年各主题大致情况」总述，**不区分小组**，500～800汉字。"
        "须覆盖：共性、三主题各自特点、对2026批改的继承提示。"
        "输出 Markdown 正文，首行用一级标题「去年2025个人课设报告批改各主题大致情况」。"
    )
    user = _user_with_limit(task, material, 500, 800)
    try:
        text, model = llm_generate(_SYSTEM_ANALYST, user)
        with open(_MD_2025, "w", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
        logger.add(TaskRecord("prep", "2025概况md", "全局", True, model, len(user), len(text)))
        logger.log(f"已写入 {_MD_2025}")
    except Exception as e:
        logger.add(TaskRecord("prep", "2025概况md", "全局", False, detail=str(e)))


def main() -> None:
    parser = argparse.ArgumentParser(description="NK2026 个人课设报告期末综合批改")
    parser.add_argument(
        "--step",
        choices=["prep", "1", "3", "all"],
        default="all",
        help="prep=从2025源素材生成概况md；1=素材梳理卡；3=最终批改；all=全部",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="已存在同 contentTitle 卡片时仍覆盖写入",
    )
    parser.add_argument(
        "--only-a",
        action="store_true",
        help="仅补第①步20张A梯子图卡（不运行prep/B/C/E，不运行第③步）",
    )
    parser.add_argument(
        "--backfill-metadata",
        action="store_true",
        help="为第①步 S5素材* 卡补齐 keyWords/score/reason/scoreSFT 等（不含 D/F 手动卡，不改正文）",
    )
    args = parser.parse_args()
    skip_existing = not args.force

    logger = RunLogger()
    logger.log(
        f"NK2026 期末综合批改启动 step={args.step} only_a={args.only_a} "
        f"backfill_metadata={args.backfill_metadata} skip_existing={skip_existing}"
    )

    if args.backfill_metadata:
        run_backfill_metadata(logger)
        logger.save_registry()
        logger.print_summary_table()
        return

    if args.only_a:
        run_step1_only_a(logger, skip_existing=skip_existing)
        logger.save_registry()
        logger.print_summary_table()
        return

    if args.step in ("prep", "all"):
        run_step_prep(logger)

    if args.step in ("1", "all"):
        run_step1(logger, skip_existing=skip_existing)

    if args.step in ("3", "all"):
        if args.step == "all":
            logger.log(
                "提示：第③步依赖「去年2025…」「今年2026批改要求」卡片；"
                "若未手动加卡，脚本将从 docs/*.md 回退读取。"
            )
        run_step3(logger, skip_existing=skip_existing)

    logger.save_registry()
    logger.print_summary_table()


if __name__ == "__main__":
    main()
