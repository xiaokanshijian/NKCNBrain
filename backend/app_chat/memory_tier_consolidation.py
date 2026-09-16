# -*- coding: utf-8 -*-
"""
短期记忆块 Summary 保存后的分层整理：每满 3 条短期摘要合并为中期记忆（LLM），
每满 3 条中期文件再合并为长期叙事记忆（LLM）。与 ESP32 结构化 {user}_LONG.txt 并存，
长期叙事写入独立文件，避免覆盖体征字段块。

模型切换（任选其一）：
- 环境变量 MEMORY_TIER_MODEL_ABBR：设为 app_chat/config/model_config/*.json 里的「abbr_name」，
  例如 Kimi、claude-3.7、DeepSeekV3、GPT4o（须已配置好 key/base，且为 OpenAI 兼容接口）。
- 未设置或配置缺失 / 调用失败时，回退为 kimi_api.make_requests（Moonshot）。
"""
import os
import re
import threading

SHORT_BLOCK_RE = re.compile(r"^(.+)_(\d{4}_\d{2}_\d{2}_\d{2}_\d{2}_\d{2})$")
TIERS_SUB = ("audio_block_summary", "tiers")
MID_SUB = "mid"
LONG_SUB = "long"
BATCH_SIZE = 3

_MID_SYSTEM = (
    "你是临床与健康场景下的记忆整理助手。请将用户给出的若干「短期记忆块摘要」"
    "合并为一段「中期记忆」：按时间顺序组织，保留关键结论、指标与趋势，去掉重复与口语废话。"
    "使用简洁中文，不超过 600 字，不要使用 Markdown 标题层级。"
)
_LONG_SYSTEM = (
    "你是临床与健康场景下的记忆整理助手。请将用户给出的若干「中期记忆」文本"
    "提炼为一段「长期记忆档案」：突出稳定特征、慢性变化趋势、需持续随访或干预的要点，"
    "避免罗列单次细节。使用简洁中文，不超过 900 字，不要使用 Markdown 标题层级。"
)


def _user_raw_base():
    return "./received_dir/user_raw_file/"


def _summary_dir(userbook):
    return os.path.join(_user_raw_base(), userbook, "audio_block_summary")


def _tiers_mid_dir(userbook):
    return os.path.join(_user_raw_base(), userbook, *TIERS_SUB, MID_SUB)


def _tiers_long_dir(userbook):
    return os.path.join(_user_raw_base(), userbook, *TIERS_SUB, LONG_SUB)


def parse_short_block_user_id(block_id):
    if not block_id:
        return None
    m = SHORT_BLOCK_RE.match(block_id.strip())
    return m.group(1) if m else None


def _sort_key_short_bid(bid):
    m = SHORT_BLOCK_RE.match(bid)
    return (m.group(2), bid) if m else (bid, bid)


def _list_short_block_ids_with_summaries(summary_dir):
    ids = []
    if not os.path.isdir(summary_dir):
        return ids
    for name in os.listdir(summary_dir):
        if not name.endswith("_Summary.txt"):
            continue
        bid = name[: -len("_Summary.txt")]
        if bid and SHORT_BLOCK_RE.match(bid):
            ids.append(bid)
    ids.sort(key=_sort_key_short_bid)
    return ids


def _short_ids_for_user(all_ids, user_id):
    prefix = user_id + "_"
    return [b for b in all_ids if b.startswith(prefix)]


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _mid_batch_filename(user_id, batch_ids):
    parts = sorted(batch_ids, key=lambda b: _sort_key_short_bid(b)[0])
    compact = []
    for b in parts:
        m = SHORT_BLOCK_RE.match(b)
        compact.append(m.group(2).replace("_", "") if m else b)
    return f"{user_id}_MID_{'_'.join(compact)}.txt"


def _list_mid_files_for_user(mid_dir, user_id):
    if not os.path.isdir(mid_dir):
        return []
    prefix = f"{user_id}_MID_"
    names = [n for n in os.listdir(mid_dir) if n.startswith(prefix) and n.endswith(".txt")]
    names.sort()
    return [os.path.join(mid_dir, n) for n in names]


def _memory_tier_model_abbr():
    return (os.environ.get("MEMORY_TIER_MODEL_ABBR") or "Kimi").strip() or "Kimi"


def _call_memory_llm(user_text, tier="mid"):
    """使用 config_manager 中已加载的 OpenAI 兼容模型；失败则回退 Kimi。"""
    from openai import OpenAI

    from app_chat import kimi_api
    from app_chat.config.config_manager import config_manager

    sys_line = _LONG_SYSTEM if tier == "long" else _MID_SYSTEM
    user_content = (user_text or "")[:100000]
    abbr = _memory_tier_model_abbr()
    mc = config_manager.configs.get(abbr)
    if mc:
        cfg = mc.config_data.get("config") or {}
        api_key = cfg.get("openai_api_key")
        base_url = (cfg.get("openai_api_base") or "").strip() or None
        model_name = cfg.get("model_name")
        if api_key and base_url and model_name:
            try:
                hp = mc.get_hyper_para()
                client_kw = {"api_key": api_key, "base_url": base_url, "timeout": 120.0}
                dh = cfg.get("default_headers")
                if isinstance(dh, dict) and dh:
                    client_kw["default_headers"] = dh
                client = OpenAI(**client_kw)
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": sys_line},
                        {"role": "user", "content": user_content},
                    ],
                    temperature=float(hp.temperature),
                    max_tokens=min(int(hp.max_tokens), 4096),
                )
                if response and response.choices:
                    out = (response.choices[0].message.content or "").strip()
                    if out:
                        return out
            except Exception as e:
                print(f"[memory_tier_consolidation] 模型「{abbr}」调用失败: {e}")

    prompt = sys_line + "\n\n--- 输入 ---\n" + user_content
    try:
        resp = kimi_api.make_requests(prompt, None, False, 0.25)
        if resp and resp.choices:
            return (resp.choices[0].message.content or "").strip()
    except Exception as e2:
        print(f"[memory_tier_consolidation] Kimi 回退调用失败: {e2}")
    return ""


def _long_narrative_path(long_dir, user_id):
    return os.path.join(long_dir, f"{user_id}_LONG_NARRATIVE.txt")


def _read_long_batch_marker(long_path):
    if not os.path.isfile(long_path):
        return None
    try:
        with open(long_path, "r", encoding="utf-8") as f:
            first = f.readline().strip()
        if first.startswith("<!--MID_BATCH:") and first.endswith("-->"):
            return first
    except Exception:
        pass
    return None


def _maybe_merge_short_to_mid(user_id, summary_dir, mid_dir):
    all_short = _list_short_block_ids_with_summaries(summary_dir)
    short_ids = _short_ids_for_user(all_short, user_id)
    n = len(short_ids)
    if n < BATCH_SIZE or n % BATCH_SIZE != 0:
        return
    batch = short_ids[-BATCH_SIZE:]
    os.makedirs(mid_dir, exist_ok=True)
    fname = _mid_batch_filename(user_id, batch)
    out_path = os.path.join(mid_dir, fname)
    if os.path.isfile(out_path):
        return
    chunks = []
    for bid in batch:
        body = _read_text(os.path.join(summary_dir, f"{bid}_Summary.txt")).strip()
        chunks.append(f"【短期块 {bid}】\n{body or '（空）'}")
    merged_in = "\n\n".join(chunks)
    text = _call_memory_llm(merged_in, tier="mid")
    if not text:
        print("[memory_tier_consolidation] 中期合并无输出，跳过写入")
        return
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[memory_tier_consolidation] 已写入中期记忆: {out_path}")


def _maybe_merge_mid_to_long(user_id, mid_dir, long_dir):
    mids = _list_mid_files_for_user(mid_dir, user_id)
    nm = len(mids)
    if nm < BATCH_SIZE or nm % BATCH_SIZE != 0:
        return
    batch_paths = mids[-BATCH_SIZE:]
    basenames = [os.path.basename(p) for p in batch_paths]
    marker = "<!--MID_BATCH:" + "|".join(basenames) + "-->"
    os.makedirs(long_dir, exist_ok=True)
    long_path = _long_narrative_path(long_dir, user_id)
    existing = _read_long_batch_marker(long_path)
    if existing == marker:
        return
    chunks = []
    for p in batch_paths:
        chunks.append(f"【中期记忆 {os.path.basename(p)}】\n{_read_text(p).strip() or '（空）'}")
    merged_in = "\n\n".join(chunks)
    text = _call_memory_llm(merged_in, tier="long")
    if not text:
        print("[memory_tier_consolidation] 长期合并无输出，跳过写入")
        return
    with open(long_path, "w", encoding="utf-8") as f:
        f.write(marker + "\n")
        f.write(text)
    print(f"[memory_tier_consolidation] 已写入长期叙事: {long_path}")


def _run_consolidation(userbook, block_id_saved):
    user_id = parse_short_block_user_id(block_id_saved)
    if not user_id:
        return
    if ".." in userbook or userbook.startswith("/"):
        return
    summary_dir = _summary_dir(userbook)
    mid_dir = _tiers_mid_dir(userbook)
    long_dir = _tiers_long_dir(userbook)
    try:
        _maybe_merge_short_to_mid(user_id, summary_dir, mid_dir)
        _maybe_merge_mid_to_long(user_id, mid_dir, long_dir)
    except Exception as e:
        print(f"[memory_tier_consolidation] 整理失败 userbook={userbook} block={block_id_saved}: {e}")
        import traceback

        traceback.print_exc()


def schedule_memory_tier_consolidation(userbook, block_id_saved):
    t = threading.Thread(target=_run_consolidation, args=(userbook, block_id_saved), daemon=True)
    t.start()


def get_memory_tier_context_for_user(userbook, user_id):
    """
    供回溯提示拼接：长期叙事全文 + 最近若干中期片段（文件名倒序取内容）。
    """
    if not userbook or not user_id or ".." in userbook:
        return {"long_narrative": "", "mid_excerpts": []}
    long_path = _long_narrative_path(_tiers_long_dir(userbook), user_id)
    long_raw = _read_text(long_path).strip()
    long_narrative = long_raw
    if long_narrative.startswith("<!--MID_BATCH:"):
        lines = long_narrative.split("\n", 1)
        long_narrative = lines[1].strip() if len(lines) > 1 else ""

    mid_dir = _tiers_mid_dir(userbook)
    mids = _list_mid_files_for_user(mid_dir, user_id)
    excerpts = []
    for p in reversed(mids[-5:]):
        excerpts.append(_read_text(p).strip())
    return {"long_narrative": long_narrative, "mid_excerpts": [e for e in excerpts if e]}
