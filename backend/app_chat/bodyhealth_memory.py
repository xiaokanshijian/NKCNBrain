"""NKCN 体联长短期记忆。

使用 SQLite 保存原始微观观测，并把日/周/月压缩为中观记忆、季度/年度/
跨年基线压缩为宏观记忆。生理时序数据优先使用可解释的数值聚合和特征距离
检索，避免仅依靠语义向量导致相近数值趋势被错配。
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable

from django.conf import settings


MEMORY_SCHEMA_VERSION = 3
DEFAULT_DB_PATH = Path(
    os.getenv(
        "BODYHEALTH_MEMORY_DB",
        str(Path(settings.BASE_DIR) / "received_dir" / "bodyhealth_memory" / "memory.db"),
    )
)

METRIC_LABELS = {
    "heart_rate_bpm": "心率",
    "respiration_rate_bpm": "呼吸率",
    "spo2_percent": "血氧",
    "systolic_bp": "收缩压",
    "diastolic_bp": "舒张压",
    "temperature_c": "体温",
    "sleep_hours": "睡眠时长",
    "sleep_quality": "睡眠质量",
    "emotion_score": "情绪自评",
    "sdnn_ms": "HRV-SDNN",
    "rmssd_ms": "HRV-RMSSD",
    "pnn50_percent": "HRV-pNN50",
    "p_precise": "精准P",
    "s_precise": "精准S",
    "i_precise": "精准I",
    "hcv_c0": "HCV-C0",
    "hcv_c1": "HCV-C1",
    "hcv_c2": "HCV-C2",
    "hcv_c3": "HCV-C3",
    "hcv_c4": "HCV-C4",
}

DISPLAY_METRICS = (
    "heart_rate_bpm",
    "respiration_rate_bpm",
    "sleep_hours",
    "sdnn_ms",
    "rmssd_ms",
    "p_precise",
    "s_precise",
    "i_precise",
)

CORE_MEMORY_METRICS = (
    "heart_rate_bpm",
    "respiration_rate_bpm",
    "sleep_hours",
    "sleep_quality",
    "emotion_score",
    "sdnn_ms",
    "rmssd_ms",
    "pnn50_percent",
    "p_precise",
    "s_precise",
    "i_precise",
    "hcv_c0",
    "hcv_c1",
    "hcv_c2",
    "hcv_c3",
    "hcv_c4",
)

METRIC_CATEGORIES = {
    "heart_rate_bpm": "即时体征",
    "respiration_rate_bpm": "即时体征",
    "spo2_percent": "即时体征",
    "systolic_bp": "即时体征",
    "diastolic_bp": "即时体征",
    "temperature_c": "即时体征",
    "sleep_hours": "恢复与睡眠",
    "sleep_quality": "恢复与睡眠",
    "emotion_score": "情绪状态",
    "sdnn_ms": "HRV自主神经",
    "rmssd_ms": "HRV自主神经",
    "pnn50_percent": "HRV自主神经",
    "p_precise": "精准PSI",
    "s_precise": "精准PSI",
    "i_precise": "精准PSI",
    "hcv_c0": "HCV谐波",
    "hcv_c1": "HCV谐波",
    "hcv_c2": "HCV谐波",
    "hcv_c3": "HCV谐波",
    "hcv_c4": "HCV谐波",
}

ABSOLUTE_TREND_THRESHOLDS = {
    "heart_rate_bpm": 3.0,
    "respiration_rate_bpm": 1.0,
    "sleep_hours": 0.4,
    "sleep_quality": 3.0,
    "emotion_score": 3.0,
    "sdnn_ms": 3.0,
    "rmssd_ms": 3.0,
    "p_precise": 0.05,
    "s_precise": 0.05,
    "i_precise": 0.05,
}


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    min_year = int(os.getenv("BODYHEALTH_MIN_MEASUREMENT_YEAR", "2020"))
    if parsed.year < min_year:
        raise ValueError(
            f"measured_at年份{parsed.year}无效，设备可能尚未完成网络校时"
        )
    if parsed.astimezone(timezone.utc) > now + timedelta(days=2):
        raise ValueError("measured_at不能晚于服务器时间两天以上")
    return parsed


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _first_number(mappings: Iterable[dict[str, Any]], keys: Iterable[str]) -> float | None:
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        for key in keys:
            value = _number(mapping.get(key))
            if value is not None:
                return value
    return None


def extract_metrics(session: dict[str, Any]) -> dict[str, float]:
    """兼容当前 ESP32 字段及后续睡眠、呼吸、情绪自评字段。"""
    vitals = session.get("vitals_avg") if isinstance(session.get("vitals_avg"), dict) else {}
    hrv = session.get("hrv_avg") if isinstance(session.get("hrv_avg"), dict) else {}
    sleep = session.get("sleep") if isinstance(session.get("sleep"), dict) else {}
    psi = session.get("psi") if isinstance(session.get("psi"), dict) else {}
    emotion = session.get("emotion") if isinstance(session.get("emotion"), dict) else {}

    candidates: dict[str, tuple[list[dict[str, Any]], tuple[str, ...]]] = {
        "heart_rate_bpm": ([vitals, session], ("heart_rate_bpm", "heart_rate", "resting_heart_rate")),
        "respiration_rate_bpm": (
            [vitals, session],
            ("respiration_rate_bpm", "respiratory_rate", "breathing_rate", "respiration_rate"),
        ),
        "spo2_percent": ([vitals, session], ("spo2_percent", "spo2")),
        "systolic_bp": ([vitals, session], ("systolic_bp", "systolic")),
        "diastolic_bp": ([vitals, session], ("diastolic_bp", "diastolic")),
        "temperature_c": ([vitals, session], ("temperature_c", "temperature")),
        "sleep_hours": (
            [sleep, vitals, session],
            ("sleep_hours", "duration_hours", "sleep_duration_hours"),
        ),
        "sleep_quality": (
            [sleep, session],
            ("sleep_quality", "quality_score", "sleep_score"),
        ),
        "emotion_score": (
            [emotion, vitals, session],
            ("emotion_score", "self_rating", "mood_score"),
        ),
        "sdnn_ms": ([hrv, session], ("sdnn_ms", "sdnn")),
        "rmssd_ms": ([hrv, session], ("rmssd_ms", "rmssd")),
        "pnn50_percent": ([hrv, session], ("pnn50_percent", "pnn50")),
        "p_precise": ([psi, session], ("p_precise",)),
        "s_precise": ([psi, session], ("s_precise",)),
        "i_precise": ([psi, session], ("i_precise",)),
    }
    metrics: dict[str, float] = {}
    for metric, (mappings, keys) in candidates.items():
        value = _first_number(mappings, keys)
        if value is not None:
            metrics[metric] = value

    hcv = session.get("hcv")
    if isinstance(hcv, list):
        for index, item in enumerate(hcv[:5]):
            if not isinstance(item, dict):
                continue
            order = int(_number(item.get("order")) or index)
            value = _number(item.get("avg"))
            if 0 <= order <= 4 and value is not None:
                metrics[f"hcv_c{order}"] = value
    elif isinstance(hcv, dict):
        for index in range(5):
            value = _number(hcv.get(f"c{index}"))
            if value is not None:
                metrics[f"hcv_c{index}"] = value
    return metrics


def extract_tags(package: dict[str, Any]) -> dict[str, Any]:
    session = package["current_session"]
    psi = session.get("psi") if isinstance(session.get("psi"), dict) else {}
    time_semantics = (
        session.get("time_semantics")
        if isinstance(session.get("time_semantics"), dict)
        else {}
    )
    sleep = session.get("sleep") if isinstance(session.get("sleep"), dict) else {}
    tags: dict[str, Any] = {
        "mode": session.get("mode"),
        "primary_node": psi.get("primary_node"),
        "season": psi.get("season") or time_semantics.get("season"),
        "solar_term": psi.get("solar_term") or time_semantics.get("solar_term"),
        "heaven_time": time_semantics.get("heaven_time") or session.get("heaven_time"),
        "earth_time": time_semantics.get("earth_time") or session.get("earth_time"),
        "human_time": time_semantics.get("human_time") or session.get("human_time"),
        "meridian_time": time_semantics.get("meridian_time") or session.get("meridian_time"),
        "acupoint_time": time_semantics.get("acupoint_time") or session.get("acupoint_time"),
        "chronos": session.get("chronos") or psi.get("chronos_load"),
        "kairos": session.get("kairos") or psi.get("kairos_load"),
        "deep_sleep": sleep.get("deep_sleep"),
        "data_origin": session.get("data_origin"),
        "scenario": session.get("scenario"),
        "data_quality": session.get("data_quality"),
    }
    kairos_memory = package.get("kairos_memory")
    if isinstance(kairos_memory, list):
        tags["recent_kairos"] = kairos_memory[:10]
    event = package.get("event") or session.get("event")
    if event:
        tags["event"] = event
    return {key: value for key, value in tags.items() if value not in (None, "", [])}


def _period_keys(moment: datetime) -> dict[str, tuple[str, str]]:
    iso_year, iso_week, _ = moment.isocalendar()
    quarter = (moment.month - 1) // 3 + 1
    return {
        "day": ("meso", moment.date().isoformat()),
        "week": ("meso", f"{iso_year}-W{iso_week:02d}"),
        "month": ("meso", f"{moment.year}-{moment.month:02d}"),
        "quarter": ("macro", f"{moment.year}-Q{quarter}"),
        "year": ("macro", str(moment.year)),
        "all": ("macro", "all"),
    }


def _aggregate(rows: list[sqlite3.Row]) -> dict[str, Any]:
    metric_series: dict[str, list[tuple[float, float]]] = {}
    tag_counts: Counter[str] = Counter()
    moments: list[float] = []
    for row in rows:
        epoch = float(row["measured_epoch"])
        moments.append(epoch)
        metrics = json.loads(row["metrics_json"])
        for key, raw_value in metrics.items():
            value = _number(raw_value)
            if value is not None:
                metric_series.setdefault(key, []).append((epoch, value))
        tags = json.loads(row["tags_json"])
        for key in ("primary_node", "season", "solar_term", "event", "scenario"):
            value = tags.get(key)
            if value not in (None, ""):
                tag_counts[f"{key}:{value}"] += 1

    metrics_summary: dict[str, Any] = {}
    for key, values_with_time in metric_series.items():
        values_with_time.sort(key=lambda item: item[0])
        values = [item[1] for item in values_with_time]
        first = values[0]
        last = values[-1]
        delta = last - first
        threshold = ABSOLUTE_TREND_THRESHOLDS.get(
            key,
            max(abs(first) * 0.05, 0.01),
        )
        direction = "稳定"
        if delta > threshold:
            direction = "上升"
        elif delta < -threshold:
            direction = "下降"
        metrics_summary[key] = {
            "count": len(values),
            "mean": round(mean(values), 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "first": round(first, 3),
            "last": round(last, 3),
            "delta": round(delta, 3),
            "direction": direction,
        }

    start_epoch = min(moments) if moments else 0
    end_epoch = max(moments) if moments else 0
    return {
        "sample_count": len(rows),
        "start_at": datetime.fromtimestamp(start_epoch, timezone.utc).isoformat() if moments else "",
        "end_at": datetime.fromtimestamp(end_epoch, timezone.utc).isoformat() if moments else "",
        "coverage_days": round((end_epoch - start_epoch) / 86400, 2) if moments else 0,
        "metrics": metrics_summary,
        "top_tags": [{"tag": tag, "count": count} for tag, count in tag_counts.most_common(8)],
    }


def _compress_summary(summary: dict[str, Any], level: str) -> dict[str, Any]:
    """按重要度归类、剪枝并抽取关键指标/关键事件，供中宏观记忆持久化。"""
    metrics = summary.get("metrics", {})
    ranked: list[tuple[float, str, dict[str, Any]]] = []
    for key, detail in metrics.items():
        threshold = ABSOLUTE_TREND_THRESHOLDS.get(
            key,
            max(abs(float(detail.get("first", 0))) * 0.05, 0.01),
        )
        change_score = abs(float(detail.get("delta", 0))) / max(threshold, 0.01)
        direction_bonus = 2.0 if detail.get("direction") != "稳定" else 0.0
        completeness_bonus = min(float(detail.get("count", 0)) / 10.0, 1.0)
        ranked.append((change_score + direction_bonus + completeness_bonus, key, detail))
    ranked.sort(key=lambda item: item[0], reverse=True)

    keep_limit = len(ranked) if level == "micro" else 16
    protected = [
        item for item in ranked if item[1] in CORE_MEMORY_METRICS
    ]
    remaining = [
        item for item in ranked if item[1] not in CORE_MEMORY_METRICS
    ]
    retained = (protected + remaining)[:keep_limit]
    retained.sort(key=lambda item: item[0], reverse=True)
    retained_metrics = {key: detail for _, key, detail in retained}
    classified: dict[str, list[str]] = {}
    for _, key, _ in retained:
        classified.setdefault(METRIC_CATEGORIES.get(key, "其他指标"), []).append(key)

    changing = [
        {
            "metric": key,
            "label": METRIC_LABELS.get(key, key),
            "direction": detail.get("direction"),
            "delta": detail.get("delta"),
            "mean": detail.get("mean"),
            "importance": round(score, 3),
        }
        for score, key, detail in retained
        if detail.get("direction") != "稳定"
    ]
    stable_baselines = [
        {
            "metric": key,
            "label": METRIC_LABELS.get(key, key),
            "mean": detail.get("mean"),
            "range": [detail.get("min"), detail.get("max")],
        }
        for _, key, detail in retained
        if detail.get("direction") == "稳定"
    ][:4]
    return {
        "sample_count": summary.get("sample_count", 0),
        "start_at": summary.get("start_at", ""),
        "end_at": summary.get("end_at", ""),
        "coverage_days": summary.get("coverage_days", 0),
        "metrics": retained_metrics,
        "classification": classified,
        "changing_key_metrics": changing,
        "stable_baselines": stable_baselines,
        "key_nodes": summary.get("top_tags", []),
        "compression": {
            "strategy": {
                "micro": "微观：字段校验、噪声筛分、风险排序、完整即时证据保留",
                "meso": "中观：阶段趋势归类、变化指标排序、稳定项剪枝、事件节点抽取",
                "macro": "宏观：跨周期基线归类、重复模式合并、低信息项剪枝、年度关键节点抽取",
            }.get(level, "分层筛分与压缩"),
            "input_metric_count": len(metrics),
            "retained_metric_count": len(retained_metrics),
            "pruned_metric_count": max(0, len(metrics) - len(retained_metrics)),
        },
    }


def _summary_text(summary: dict[str, Any], level: str) -> str:
    if not summary.get("sample_count"):
        return "暂无历史数据。"
    pieces = [
        f"{summary['sample_count']}次记录/{summary.get('coverage_days', 0)}天覆盖"
    ]
    metrics = summary.get("metrics", {})
    for key in DISPLAY_METRICS:
        detail = metrics.get(key)
        if not detail:
            continue
        pieces.append(
            f"{METRIC_LABELS[key]}均值{detail['mean']}、较首期{detail['direction']}"
            f"({detail['delta']:+g})"
        )
    prefix = {
        "micro": "微观即时摘要",
        "meso": "中观阶段摘要",
        "macro": "宏观基线摘要",
    }.get(level, "分层记忆摘要")
    return f"{prefix}：" + "；".join(pieces) + "。"


class BodyHealthMemoryStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=15000")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS observations (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    measured_at TEXT NOT NULL,
                    measured_epoch REAL NOT NULL,
                    local_day TEXT NOT NULL,
                    iso_week TEXT NOT NULL,
                    month_key TEXT NOT NULL,
                    quarter_key TEXT NOT NULL,
                    year_key TEXT NOT NULL,
                    metrics_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, session_id)
                );
                CREATE INDEX IF NOT EXISTS idx_bodyhealth_observation_time
                    ON observations(user_id, measured_epoch);
                CREATE INDEX IF NOT EXISTS idx_bodyhealth_observation_period
                    ON observations(user_id, iso_week, month_key, quarter_key, year_key);

                CREATE TABLE IF NOT EXISTS period_memories (
                    user_id TEXT NOT NULL,
                    level TEXT NOT NULL,
                    period_type TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    sample_count INTEGER NOT NULL,
                    start_at TEXT NOT NULL,
                    end_at TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, period_type, period_key)
                );

                CREATE TABLE IF NOT EXISTS advice_history (
                    user_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    advice TEXT NOT NULL,
                    memory_state_json TEXT NOT NULL,
                    outcome_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, session_id)
                );
                """
            )

    def remember_and_recall(self, package: dict[str, Any]) -> dict[str, Any]:
        session = package["current_session"]
        user_id = str(package["user_id"])
        session_id = str(package["session_id"])
        measured = _parse_time(session["measured_at"])
        keys = _period_keys(measured)
        metrics = extract_metrics(session)
        tags = extract_tags(package)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO observations(
                    user_id, session_id, device_id, measured_at, measured_epoch,
                    local_day, iso_week, month_key, quarter_key, year_key,
                    metrics_json, tags_json, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    device_id=excluded.device_id,
                    measured_at=excluded.measured_at,
                    measured_epoch=excluded.measured_epoch,
                    metrics_json=excluded.metrics_json,
                    tags_json=excluded.tags_json,
                    payload_json=excluded.payload_json
                """,
                (
                    user_id,
                    session_id,
                    str(session["device_id"]),
                    measured.isoformat(),
                    measured.timestamp(),
                    keys["day"][1],
                    keys["week"][1],
                    keys["month"][1],
                    keys["quarter"][1],
                    keys["year"][1],
                    json.dumps(metrics, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(tags, ensure_ascii=False, separators=(",", ":")),
                    json.dumps(session, ensure_ascii=False, separators=(",", ":")),
                    now,
                ),
            )
            self._apply_feedback(db, package, user_id, now)
            for period_type, (level, period_key) in keys.items():
                self._refresh_period(db, user_id, level, period_type, period_key, now)
            db.commit()
            return self._recall(db, user_id, session_id, measured, metrics, tags)

    def _apply_feedback(
        self,
        db: sqlite3.Connection,
        package: dict[str, Any],
        user_id: str,
        now: str,
    ) -> None:
        feedback = package.get("advice_feedback")
        if not isinstance(feedback, dict):
            return
        target_session = str(feedback.get("session_id") or "").strip()
        if not target_session:
            return
        db.execute(
            """
            UPDATE advice_history
            SET outcome_json = ?, updated_at = ?
            WHERE user_id = ? AND session_id = ?
            """,
            (
                json.dumps(feedback, ensure_ascii=False, separators=(",", ":")),
                now,
                user_id,
                target_session,
            ),
        )

    def _period_rows(
        self,
        db: sqlite3.Connection,
        user_id: str,
        period_type: str,
        period_key: str,
    ) -> list[sqlite3.Row]:
        columns = {
            "day": "local_day",
            "week": "iso_week",
            "month": "month_key",
            "quarter": "quarter_key",
            "year": "year_key",
        }
        if period_type == "all":
            return db.execute(
                "SELECT * FROM observations WHERE user_id = ? ORDER BY measured_epoch",
                (user_id,),
            ).fetchall()
        column = columns[period_type]
        return db.execute(
            f"SELECT * FROM observations WHERE user_id = ? AND {column} = ? "
            "ORDER BY measured_epoch",
            (user_id, period_key),
        ).fetchall()

    def _refresh_period(
        self,
        db: sqlite3.Connection,
        user_id: str,
        level: str,
        period_type: str,
        period_key: str,
        now: str,
    ) -> None:
        summary = _compress_summary(
            _aggregate(self._period_rows(db, user_id, period_type, period_key)),
            level,
        )
        db.execute(
            """
            INSERT INTO period_memories(
                user_id, level, period_type, period_key, sample_count,
                start_at, end_at, summary_json, summary_text, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, period_type, period_key) DO UPDATE SET
                sample_count=excluded.sample_count,
                start_at=excluded.start_at,
                end_at=excluded.end_at,
                summary_json=excluded.summary_json,
                summary_text=excluded.summary_text,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                level,
                period_type,
                period_key,
                summary["sample_count"],
                summary["start_at"],
                summary["end_at"],
                json.dumps(summary, ensure_ascii=False, separators=(",", ":")),
                _summary_text(summary, level),
                now,
            ),
        )

    def _window_summary(
        self,
        db: sqlite3.Connection,
        user_id: str,
        end: datetime,
        days: int,
        level: str,
    ) -> dict[str, Any]:
        rows = db.execute(
            """
            SELECT * FROM observations
            WHERE user_id = ? AND measured_epoch BETWEEN ? AND ?
            ORDER BY measured_epoch
            """,
            (user_id, (end - timedelta(days=days)).timestamp(), end.timestamp()),
        ).fetchall()
        return _compress_summary(_aggregate(rows), level)

    def _macro_memory(
        self,
        db: sqlite3.Connection,
        user_id: str,
        measured: datetime,
    ) -> dict[str, Any]:
        keys = _period_keys(measured)
        rows = db.execute(
            """
            SELECT period_type, period_key, summary_json, summary_text
            FROM period_memories
            WHERE user_id = ? AND level = 'macro'
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
        indexed = {
            (row["period_type"], row["period_key"]): {
                "summary": json.loads(row["summary_json"]),
                "text": row["summary_text"],
            }
            for row in rows
        }
        quarter = indexed.get(("quarter", keys["quarter"][1]), {})
        year = indexed.get(("year", keys["year"][1]), {})
        lifetime = indexed.get(("all", "all"), {})
        q_summary = quarter.get("summary", {})
        y_summary = year.get("summary", {})
        all_summary = lifetime.get("summary", {})
        year_count = db.execute(
            "SELECT COUNT(DISTINCT year_key) FROM observations WHERE user_id = ?",
            (user_id,),
        ).fetchone()[0]
        return {
            "quarter": quarter,
            "year": year,
            "long_term": lifetime,
            "eligibility": {
                "quarter_pattern": bool(
                    q_summary.get("sample_count", 0) >= 8
                    and q_summary.get("coverage_days", 0) >= 30
                ),
                "year_pattern": bool(
                    y_summary.get("sample_count", 0) >= 20
                    and y_summary.get("coverage_days", 0) >= 90
                ),
                "cross_year_stable_pattern": bool(
                    year_count >= 2
                    and all_summary.get("sample_count", 0) >= 40
                    and all_summary.get("coverage_days", 0) >= 365
                ),
            },
            "distinct_years": int(year_count),
        }

    def _similar_memories(
        self,
        db: sqlite3.Connection,
        user_id: str,
        session_id: str,
        current_metrics: dict[str, float],
        current_tags: dict[str, Any],
    ) -> list[dict[str, Any]]:
        rows = db.execute(
            """
            SELECT session_id, measured_at, metrics_json, tags_json
            FROM observations
            WHERE user_id = ? AND session_id <> ?
            ORDER BY measured_epoch DESC LIMIT 1000
            """,
            (user_id, session_id),
        ).fetchall()
        if not rows or not current_metrics:
            return []

        histories = [
            (
                row,
                json.loads(row["metrics_json"]),
                json.loads(row["tags_json"]),
            )
            for row in rows
        ]
        per_metric_values: dict[str, list[float]] = {}
        for _, metrics, _ in histories:
            for key, value in metrics.items():
                number = _number(value)
                if number is not None:
                    per_metric_values.setdefault(key, []).append(number)
        scales = {
            key: max(pstdev(values), ABSOLUTE_TREND_THRESHOLDS.get(key, 0.05))
            for key, values in per_metric_values.items()
            if values
        }

        ranked: list[tuple[float, sqlite3.Row, dict[str, Any], dict[str, Any]]] = []
        for row, metrics, tags in histories:
            distances = []
            for key, current_value in current_metrics.items():
                historic_value = _number(metrics.get(key))
                if historic_value is None:
                    continue
                distances.append(abs(current_value - historic_value) / scales.get(key, 1.0))
            if not distances:
                continue
            distance = mean(distances)
            for tag_key in ("primary_node", "solar_term", "event", "season"):
                if current_tags.get(tag_key) and current_tags.get(tag_key) == tags.get(tag_key):
                    distance *= 0.8
            ranked.append((distance, row, metrics, tags))
        ranked.sort(key=lambda item: item[0])
        return [
            {
                "session_id": row["session_id"],
                "measured_at": row["measured_at"],
                "similarity": round(1 / (1 + distance), 3),
                "metrics": {
                    key: value
                    for key, value in metrics.items()
                    if key in DISPLAY_METRICS or key.startswith("hcv_")
                },
                "tags": tags,
            }
            for distance, row, metrics, tags in ranked[:3]
        ]

    def _recall(
        self,
        db: sqlite3.Connection,
        user_id: str,
        session_id: str,
        measured: datetime,
        current_metrics: dict[str, float],
        current_tags: dict[str, Any],
    ) -> dict[str, Any]:
        micro = self._window_summary(db, user_id, measured, 1, "micro")
        week = self._window_summary(db, user_id, measured, 7, "meso")
        month = self._window_summary(db, user_id, measured, 30, "meso")
        micro["summary_text"] = _summary_text(micro, "micro")
        week["summary_text"] = _summary_text(week, "meso")
        month["summary_text"] = _summary_text(month, "meso")
        macro = self._macro_memory(db, user_id, measured)
        recent_advice = db.execute(
            """
            SELECT session_id, advice, outcome_json, created_at
            FROM advice_history
            WHERE user_id = ? ORDER BY created_at DESC LIMIT 3
            """,
            (user_id,),
        ).fetchall()
        return {
            "memory_schema_version": MEMORY_SCHEMA_VERSION,
            "user_id": user_id,
            "current_session_id": session_id,
            "micro": {
                "definition": "分钟、小时尺度的即时状态",
                "current_metrics": current_metrics,
                "time_semantics": current_tags,
                "last_24_hours": micro,
            },
            "meso": {
                "definition": "日、周、月尺度的阶段性趋势",
                "last_7_days": week,
                "last_30_days": month,
                "eligible": week.get("sample_count", 0) >= 2,
            },
            "macro": {
                "definition": "季度、年度及跨年尺度的个人基线与稳定规律",
                **macro,
            },
            "similar_historical_states": self._similar_memories(
                db,
                user_id,
                session_id,
                current_metrics,
                current_tags,
            ),
            "recent_advice": [
                {
                    "session_id": row["session_id"],
                    "advice": row["advice"][:500],
                    "outcome": (
                        json.loads(row["outcome_json"])
                        if row["outcome_json"]
                        else None
                    ),
                    "created_at": row["created_at"],
                }
                for row in recent_advice
            ],
            "memory_state": {
                "micro_samples_24h": micro.get("sample_count", 0),
                "meso_samples_7d": week.get("sample_count", 0),
                "meso_samples_30d": month.get("sample_count", 0),
                "macro_quarter_ready": macro["eligibility"]["quarter_pattern"],
                "macro_year_ready": macro["eligibility"]["year_pattern"],
                "macro_cross_year_ready": macro["eligibility"][
                    "cross_year_stable_pattern"
                ],
            },
        }

    def record_advice(
        self,
        user_id: str,
        session_id: str,
        advice: str,
        memory_state: dict[str, Any],
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            db.execute(
                """
                INSERT INTO advice_history(
                    user_id, session_id, advice, memory_state_json,
                    outcome_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, NULL, ?, ?)
                ON CONFLICT(user_id, session_id) DO UPDATE SET
                    advice=excluded.advice,
                    memory_state_json=excluded.memory_state_json,
                    updated_at=excluded.updated_at
                """,
                (
                    user_id,
                    session_id,
                    advice,
                    json.dumps(memory_state, ensure_ascii=False, separators=(",", ":")),
                    now,
                    now,
                ),
            )

    def record_feedback(self, user_id: str, feedback: dict[str, Any]) -> bool:
        """把建议是否执行及次日结果写回长期记忆。"""
        target_session = str(feedback.get("session_id") or "").strip()
        if not target_session:
            raise ValueError("feedback.session_id不能为空")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as db:
            cursor = db.execute(
                """
                UPDATE advice_history
                SET outcome_json = ?, updated_at = ?
                WHERE user_id = ? AND session_id = ?
                """,
                (
                    json.dumps(feedback, ensure_ascii=False, separators=(",", ":")),
                    now,
                    user_id,
                    target_session,
                ),
            )
            return cursor.rowcount == 1
