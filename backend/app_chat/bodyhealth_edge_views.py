"""树莓派体联边缘节点与 NKCN 之间的同步接口。"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from app_chat import gpt4_api
from app_chat.bodyhealth_memory import (
    DEFAULT_DB_PATH,
    MEMORY_SCHEMA_VERSION,
    BodyHealthMemoryStore,
)


EDGE_SOURCE = "raspberry_pi_edge"
MAX_REQUEST_BYTES = int(os.getenv("BODYHEALTH_EDGE_MAX_BYTES", str(512 * 1024)))
ARCHIVE_ROOT = Path(
    os.getenv(
        "BODYHEALTH_EDGE_ARCHIVE_DIR",
        str(Path(settings.BASE_DIR) / "received_dir" / "bodyhealth_edge"),
    )
)
MEMORY_DB_PATH = DEFAULT_DB_PATH

REQUIRED_SESSION_FIELDS = {
    "device_id",
    "user_id",
    "session_id",
    "measured_at",
    "vitals_avg",
    "hrv_avg",
    "hcv",
    "psi",
}


def _safe_component(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(value))[:100] or "unknown"


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _archive_path(user_id: str, session_id: str) -> Path:
    return (
        ARCHIVE_ROOT
        / _safe_component(user_id)
        / f"{_safe_component(session_id)}.json"
    )


def _authorized(request) -> bool:
    expected = os.getenv("BODYHEALTH_EDGE_TOKEN", "").strip()
    if not expected:
        return True
    auth = request.headers.get("Authorization", "")
    bearer = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
    provided = bearer or request.headers.get("X-Bodyhealth-Token", "").strip()
    return bool(provided) and hmac.compare_digest(provided, expected)


def _validate_package(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("请求体必须是JSON对象")
    if data.get("source") != EDGE_SOURCE:
        raise ValueError(f"source必须为{EDGE_SOURCE}")
    if str(data.get("schema_version", "1")) != "1":
        raise ValueError("当前仅支持schema_version=1")

    current = data.get("current_session")
    if not isinstance(current, dict):
        raise ValueError("current_session必须是JSON对象")
    missing = REQUIRED_SESSION_FIELDS - current.keys()
    if missing:
        raise ValueError(f"current_session缺少字段: {sorted(missing)}")

    user_id = str(data.get("user_id") or current.get("user_id") or "").strip()
    session_id = str(data.get("session_id") or current.get("session_id") or "").strip()
    if not user_id or not session_id:
        raise ValueError("user_id和session_id不能为空")
    if str(current.get("user_id")) != user_id:
        raise ValueError("外层user_id与current_session.user_id不一致")
    if str(current.get("session_id")) != session_id:
        raise ValueError("外层session_id与current_session.session_id不一致")

    chronos = data.get("chronos_memory", [])
    kairos = data.get("kairos_memory", [])
    if not isinstance(chronos, list) or not isinstance(kairos, list):
        raise ValueError("chronos_memory和kairos_memory必须是数组")
    if len(chronos) > 31 or len(kairos) > 100:
        raise ValueError("记忆数据超过限制")
    return data


def _value(value: Any, digits: int = 2) -> str:
    if value is None:
        return "未上报"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _current_evidence(data: dict[str, Any], memory: dict[str, Any]) -> str:
    current = data["current_session"]
    metrics = memory.get("micro", {}).get("current_metrics", {})
    hcv_values = [
        f"C{index}={_value(metrics.get(f'hcv_c{index}'))}" for index in range(5)
    ]
    time_tags = memory.get("micro", {}).get("time_semantics", {})
    five_times = "、".join(
        f"{label}={time_tags.get(key)}"
        for key, label in (
            ("heaven_time", "天时"),
            ("earth_time", "地时"),
            ("human_time", "人时"),
            ("meridian_time", "经时"),
            ("acupoint_time", "穴时"),
        )
        if time_tags.get(key) not in (None, "")
    )
    if not five_times:
        five_times = "本次未上报完整三时/五时时间坐标"
    return "；".join(
        [
            (
                "PSI"
                f"(P={_value(metrics.get('p_precise'))},"
                f"S={_value(metrics.get('s_precise'))},"
                f"I={_value(metrics.get('i_precise'))})"
            ),
            (
                "HRV"
                f"(SDNN={_value(metrics.get('sdnn_ms'))}ms,"
                f"RMSSD={_value(metrics.get('rmssd_ms'))}ms,"
                f"pNN50={_value(metrics.get('pnn50_percent'))}%)"
            ),
            "HCV(" + ",".join(hcv_values) + ")",
            (
                f"心率={_value(metrics.get('heart_rate_bpm'))}bpm，"
                f"呼吸={_value(metrics.get('respiration_rate_bpm'))}次/分，"
                f"睡眠={_value(metrics.get('sleep_hours'))}小时"
            ),
            f"三时/五时：{five_times}",
            (
                f"Chronos={_value(time_tags.get('chronos'))}，"
                f"Kairos={_value(time_tags.get('kairos'))}，"
                f"当前节点={_value(time_tags.get('primary_node'))}"
            ),
            (
                f"数据来源={_value(current.get('data_origin'))}，"
                f"场景={_value(current.get('scenario'))}，"
                f"质量标记={_value(current.get('data_quality'))}"
            ),
            f"有效样本={_value(current.get('sample_count'), 0)}组",
        ]
    )


def _key_nodes_text(memory_item: dict[str, Any]) -> str:
    summary = memory_item.get("summary", {})
    nodes = summary.get("key_nodes", []) if isinstance(summary, dict) else []
    useful = []
    for node in nodes:
        raw_tag = str(node.get("tag") or "")
        if raw_tag.startswith(("event:", "scenario:", "solar_term:", "season:")):
            useful.append(f"{raw_tag.replace(':', '=', 1)}重复{node.get('count', 0)}次")
    return "；".join(useful)


def _macro_fallback(memory: dict[str, Any]) -> str:
    macro = memory.get("macro", {})
    eligibility = macro.get("eligibility", {})
    if eligibility.get("cross_year_stable_pattern"):
        long_term = macro.get("long_term", {})
        nodes = _key_nodes_text(long_term)
        return "；".join(
            part
            for part in (
                str(long_term.get("text") or "已形成跨年个人基线和重复事件规律。"),
                f"跨{macro.get('distinct_years', 0)}年关键节点归类结果：{nodes}"
                if nodes
                else "",
            )
            if part
        )
    if eligibility.get("year_pattern"):
        year = macro.get("year", {})
        nodes = _key_nodes_text(year)
        return "；".join(
            part
            for part in (
                str(year.get("text") or "已形成年度个人基线。"),
                f"年度关键节点：{nodes}" if nodes else "",
            )
            if part
        )
    if eligibility.get("quarter_pattern"):
        quarter = macro.get("quarter", {})
        nodes = _key_nodes_text(quarter)
        return "；".join(
            part
            for part in (
                str(quarter.get("text") or "已形成季度个人基线。"),
                f"季度关键节点：{nodes}" if nodes else "",
            )
            if part
        )
    return "宏观层仅保留数据库中经过跨周期重复验证的个人规律，孤立记录已被剪枝。"


def _meso_fallback(memory: dict[str, Any]) -> str:
    meso = memory.get("meso", {})
    week = meso.get("last_7_days", {})
    if meso.get("eligible"):
        nodes = _key_nodes_text({"summary": week})
        return "；".join(
            part
            for part in (
                str(week.get("summary_text") or "已形成近一周阶段性趋势。"),
                f"本周关键节点：{nodes}" if nodes else "",
            )
            if part
        )
    return "中观层仅保留日周窗口内连续出现的趋势和阶段事件，孤立波动已被剪枝。"


def _extract_section(text: str, title: str, following: list[str]) -> str:
    endings = "|".join(re.escape(f"【{name}】") for name in following)
    pattern = rf"【{re.escape(title)}】\s*(.*?)(?={endings}|$)" if endings else (
        rf"【{re.escape(title)}】\s*(.*)$"
    )
    match = re.search(pattern, text, flags=re.DOTALL)
    return match.group(1).strip() if match else ""


def _remove_confidence_content(text: str) -> str:
    """产品输出不展示可信度/置信度区块，即使模型偶尔仍生成也会删除。"""
    cleaned = re.sub(
        r"(?ims)^\s*(?:#{1,6}\s*)?(?:【\s*)?(?:可信度|置信度)(?:\s*】)?"
        r"\s*[:：]?\s*$.*?(?=^\s*(?:#{1,6}\s+|【)|\Z)",
        "",
        str(text or ""),
    )
    cleaned = re.sub(
        r"(?im)^\s*[-*]?\s*(?:\*\*)?(?:可信度|置信度)(?:\*\*)?\s*[:：].*$",
        "",
        cleaned,
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _stabilize_advice(
    advice: str,
    data: dict[str, Any],
    memory: dict[str, Any],
) -> str:
    """强制输出宏观→中观→微观，并用确定性证据防止关键分析丢失。"""
    raw = _remove_confidence_content(str(advice or "")).strip()
    macro_model = _extract_section(raw, "宏观", ["中观", "微观"])
    meso_model = _extract_section(raw, "中观", ["微观"])
    micro_model = _extract_section(raw, "微观", [])
    if not micro_model:
        micro_model = raw

    eligibility = memory.get("macro", {}).get("eligibility", {})
    macro_ready = any(bool(value) for value in eligibility.values())
    macro = re.sub(r"\s+", " ", macro_model).strip() if macro_ready else ""
    if not macro:
        macro = _macro_fallback(memory)

    meso_ready = bool(memory.get("meso", {}).get("eligible"))
    meso = re.sub(r"\s+", " ", meso_model).strip() if meso_ready else ""
    if not meso:
        meso = _meso_fallback(memory)

    evidence = _current_evidence(data, memory)
    micro_model = _remove_confidence_content(micro_model)
    micro_model = re.sub(
        r"^(数据依据|核心数据|证据)\s*[：:][^\n]*\n?",
        "",
        micro_model,
        count=1,
    ).strip()
    if not micro_model:
        micro_model = "请结合本次即时数据继续观察，并在出现明显不适时及时寻求专业帮助。"
    return "\n".join(
        [
            "【宏观】",
            macro,
            "【中观】",
            meso,
            "【微观】",
            f"数据依据：{evidence}。",
            micro_model,
        ]
    )


def _build_prompt(data: dict[str, Any], memory: dict[str, Any]) -> str:
    current = data["current_session"]
    task = str(data.get("task") or "生成简洁、可执行的体联健康建议")
    chronos = data.get("chronos_memory", [])[-7:]
    kairos = data.get("kairos_memory", [])[:20]
    return "\n".join(
        [
            "请根据以下体联设备数据生成中文建议。",
            "这是一个分层时序记忆分析任务。必须严格区分证据尺度，禁止把单次数据包装成长期规律。",
            "记忆不是被动存储：第二阶段语义总结必须执行筛分、压缩、归类、剪枝和关键节点抽取。",
            "【输出格式（标题和顺序必须完全一致）】",
            "【宏观】讨论季度、年度、跨年个人基线和重复事件模式；不限制句数，输出所有与本次判断有关的内容。",
            "【中观】讨论日、周、月趋势及阶段事件；不限制句数，输出所有与本次判断有关的内容。",
            "【微观】主体：分析本次分钟/小时状态，说明主要影响来源，并给出情绪安抚和具体建议。",
            "若下方设备task仍带有旧版“一至两句话”要求，以本提示中的“不限制句数”为准。",
            "【分层智能压缩方法】",
            "A. 微观以梳理和筛分为主：校验字段、去除噪声、按风险和相关性排序；"
            "保留当前PSI、五时、HRV、HCV、心率、呼吸、睡眠及事件的完整证据链。",
            "B. 中观进一步压缩和归类：合并重复的日记录，按睡眠/恢复、HRV、情绪、"
            "考试压力等主题聚类，剪除稳定且与当前问题无关的低信息项，抽取趋势转折和连续异常节点。",
            "C. 宏观执行跨周期压缩：合并年度同周期模式，归纳长期个人基线和季节性规律，"
            "剪除偶发事件，抽取跨年重复出现的关键节点及恢复条件。",
            "分析约束：",
            "1. 精准PSI必须综合：基础PSI + 三时/五时背景 + HRV/HCV与睡眠校准"
            " + Chronos/Kairos事件修正 + 长短期记忆参照。",
            "2. 不得遗漏P/S/I、五时（天时/地时/人时/经时/穴时）、HRV、HCV、"
            "心率、呼吸、睡眠、Chronos和Kairos。必须区分实测、算法推导和演示补全字段；"
            "演示补全数据可用于最小场景验证，但不得冒充实测。",
            "3. 说明当前状态与个人基线的差异，并区分基础周期、连续缺觉、特殊事件和长期规律的作用。",
            "4. 禁止输出“可信度”或“置信度”标题、等级及相关段落，也不要向用户罗列样本不足。",
            "5. 面向普通用户表达：少用术语；必须说清楚“现在可能怎么了、为什么会这样、接下来怎么做”。"
            "专业指标首次出现时要用一句通俗话解释。",
            "6. 先安抚用户情绪，不夸大、不责备、不制造恐慌；告诉用户短期波动通常可以通过休息、"
            "降低任务强度、呼吸放松和寻求支持逐步缓解。",
            "7. 给出分时行动：现在可以做什么、今晚怎么安排、明天复测什么；建议必须具体、温和且可执行。",
            "8. 保护用户健康：不作疾病诊断；异常指标建议安静复测。若持续明显不适、情绪长时间低落、"
            "无法正常学习生活或出现伤害自己的想法，应立即告诉可信任的人并尽快联系专业人员或就医。",
            "9. 总体控制在900字以内，微观部分为主体。",
            f"任务：{task}",
            "【本次测量】",
            json.dumps(current, ensure_ascii=False, indent=2),
            "【NKCN分层长短期记忆（已压缩）】",
            json.dumps(memory, ensure_ascii=False, indent=2),
            "【最近七日Chronos记忆】",
            json.dumps(chronos, ensure_ascii=False, indent=2),
            "【最近Kairos节点】",
            json.dumps(kairos, ensure_ascii=False, indent=2),
        ]
    )


def _generate_advice(data: dict[str, Any], memory: dict[str, Any]) -> str:
    fake_advice = os.getenv("BODYHEALTH_EDGE_FAKE_ADVICE", "").strip()
    if fake_advice:
        return _stabilize_advice(fake_advice, data, memory)
    system_prompt = (
        "你是NKCN体联长短期记忆与精准PSI分析助手。你必须基于证据区分宏观、"
        "中观、微观时间尺度，将五时时间语义、HRV、HCV、睡眠、Chronos、Kairos"
        "与个人历史基线共同用于判断。微观以梳理筛分为主；中观和宏观必须进一步执行"
        "压缩、归类、剪枝、重复模式合并和关键节点抽取。宏观与中观不限制句数，所有"
        "相关证据均可输出。禁止输出可信度或置信度。面向普通用户先进行温和的情绪安抚，"
        "用通俗语言说明原因，再给出现在、今晚和明天可以执行的缓解步骤。"
        "你提供健康数据解释和生活方式建议，不作医疗诊断。"
    )
    advice = gpt4_api.make_gpt4o_text_requests(
        _build_prompt(data, memory),
        system_prompt=system_prompt,
        use_fixed_params=True,
    )
    advice = str(advice or "").strip()
    if not advice:
        raise RuntimeError("模型未返回建议内容")
    return _stabilize_advice(advice, data, memory)


@csrf_exempt
@require_POST
def bodyhealth_edge_sync(request):
    """接收树莓派整理包，同步返回可回传 ESP32 的建议。"""
    if not _authorized(request):
        return JsonResponse(
            {"status": "fail", "error": "unauthorized"},
            status=401,
        )
    if len(request.body) > MAX_REQUEST_BYTES:
        return JsonResponse(
            {"status": "fail", "error": "request_too_large"},
            status=413,
        )

    try:
        data = _validate_package(json.loads(request.body.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JsonResponse(
            {"status": "fail", "error": "invalid_payload", "message": str(exc)},
            status=400,
        )

    user_id = str(data["user_id"])
    session_id = str(data["session_id"])
    archive_path = _archive_path(user_id, session_id)

    # 同一会话重试时直接复用已生成建议，避免重复调用模型。
    if archive_path.exists():
        try:
            archived = json.loads(archive_path.read_text(encoding="utf-8"))
            archived_response = archived.get("response", {})
            advice = str(archived_response.get("advice") or "").strip()
            if (
                advice
                and archived_response.get("memory_schema_version")
                == MEMORY_SCHEMA_VERSION
            ):
                return JsonResponse(
                    {
                        "status": "success",
                        "schema_version": 1,
                        "memory_schema_version": MEMORY_SCHEMA_VERSION,
                        "session_id": session_id,
                        "advice": advice,
                        "memory_state": archived_response.get("memory_state", {}),
                        "cached": True,
                    }
                )
        except (OSError, json.JSONDecodeError):
            pass

    try:
        memory_store = BodyHealthMemoryStore(MEMORY_DB_PATH)
        memory = memory_store.remember_and_recall(data)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "fail",
                "error": "memory_failed",
                "message": str(exc),
                "session_id": session_id,
            },
            status=500,
        )

    try:
        advice = _generate_advice(data, memory)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "fail",
                "error": "analysis_failed",
                "message": str(exc),
                "session_id": session_id,
            },
            status=502,
        )

    memory_state = memory.get("memory_state", {})
    response_payload = {
        "status": "success",
        "schema_version": 1,
        "memory_schema_version": MEMORY_SCHEMA_VERSION,
        "session_id": session_id,
        "advice": advice,
        "memory_state": memory_state,
        "cached": False,
    }
    try:
        memory_store.record_advice(user_id, session_id, advice, memory_state)
    except Exception as exc:
        return JsonResponse(
            {
                "status": "fail",
                "error": "memory_write_failed",
                "message": str(exc),
                "session_id": session_id,
            },
            status=500,
        )

    archive = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "request_sha256": hashlib.sha256(request.body).hexdigest(),
        "request": data,
        "memory_context": memory,
        "response": response_payload,
    }
    try:
        _atomic_write_json(archive_path, archive)
    except OSError as exc:
        return JsonResponse(
            {
                "status": "fail",
                "error": "archive_failed",
                "message": str(exc),
                "session_id": session_id,
            },
            status=500,
        )
    return JsonResponse(response_payload)


@csrf_exempt
@require_POST
def bodyhealth_edge_feedback(request):
    """记录建议执行情况，供后续宏观/中观记忆检索与效果比较。"""
    if not _authorized(request):
        return JsonResponse({"status": "fail", "error": "unauthorized"}, status=401)
    if len(request.body) > MAX_REQUEST_BYTES:
        return JsonResponse({"status": "fail", "error": "request_too_large"}, status=413)
    try:
        data = json.loads(request.body.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("请求体必须是JSON对象")
        if data.get("source") != EDGE_SOURCE:
            raise ValueError(f"source必须为{EDGE_SOURCE}")
        user_id = str(data.get("user_id") or "").strip()
        session_id = str(data.get("session_id") or "").strip()
        if not user_id or not session_id:
            raise ValueError("user_id和session_id不能为空")
        feedback = {
            "session_id": session_id,
            "recorded_at": str(
                data.get("recorded_at") or datetime.now(timezone.utc).isoformat()
            ),
            "followed": data.get("followed"),
            "outcome": data.get("outcome"),
            "note": data.get("note"),
        }
        memory_store = BodyHealthMemoryStore(MEMORY_DB_PATH)
        updated = memory_store.record_feedback(user_id, feedback)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        return JsonResponse(
            {"status": "fail", "error": "invalid_payload", "message": str(exc)},
            status=400,
        )
    except Exception as exc:
        return JsonResponse(
            {"status": "fail", "error": "memory_write_failed", "message": str(exc)},
            status=500,
        )
    if not updated:
        return JsonResponse(
            {
                "status": "fail",
                "error": "advice_not_found",
                "message": "未找到对应session_id的历史建议",
            },
            status=404,
        )
    return JsonResponse(
        {
            "status": "success",
            "memory_schema_version": MEMORY_SCHEMA_VERSION,
            "user_id": user_id,
            "session_id": session_id,
        }
    )
