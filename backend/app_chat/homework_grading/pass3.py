"""Pass3 双科交叉诊断（nkcn 自有，改编自 yq v2.0 grader_pass3.py + prompts Pass3）。

输入两份已完成批改的同一学生不同学科作业（各自的 memory + pass2 report），
输出跨学科迁移识别 / 共性习惯诊断 / 双科练习优先级 + summary。
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from app_chat.homework_grading.llm_clients import (
    _deepseek_client,
    _loads_json_with_retry_text,
    homework_deepseek_model,
)
from app_chat.homework_grading.prompts import (
    _filter_curriculum_by_memory,
    _format_curriculum_block,
    _format_zone_table,
)
from app_chat.homework_grading.curriculum import load_curriculum_entries
from app_chat.homework_grading.utils import SUBJECT_LABELS, safe_json_dump


PASS3_SYSTEM_BASE = '''你是一位中小学跨学科学习诊断专家。基于同一学生两份不同学科作业的批改记忆与三区报告，输出三维交叉分析：（1）跨学科知识点迁移识别；（2）共性学习习惯诊断；（3）双科练习优先级建议。你只输出 JSON 对象，不输出 Markdown、解释或额外文本。

## 任务范围

学生：{student_id}
学科 A：{subject_a}（共 {kp_count_a} 条相关课标）
学科 B：{subject_b}（共 {kp_count_b} 条相关课标）

## 三维分析定义

1. **迁移识别（transfer_links）**：两学科中可相互支撑或迁移的知识点对。仅当存在合理认知关联时记录，不强行配对，不杜撰。
2. **学习习惯诊断（habit_diagnosis）**：跨两科出现的共性错误模式或答题倾向。证据需可追溯到具体题号。
3. **优先级建议（priority）**：综合两科盲区/内耗区/最近发展区，按可干预性 + 认知收益排序，列出最多 3 条最该优先突破的方向，每条标注学科与课标 id。

## 三区与课标参考（仅列学生实际涉及的条目）

### 学科 A ({subject_a}) 课标
{curriculum_block_a}

### 学科 B ({subject_b}) 课标
{curriculum_block_b}

### 三区定义
{zone_table}

## L4 约束（避免幻觉）

- transfer_links 中引用的 knowledge_point 必须出现在对应学科的 memory 中，禁止杜撰。
- 引用的课标 id 必须出现在上方课标列表中；不确定则留空数组并写明"课标证据不足"。
- 引用的 question_ids 必须来自对应学科的 memory.error_questions。
- 若两科确无可识别的迁移关联，transfer_links 输出空数组而非编造。

## 三级筛分（输出规范）

- priority 最多 3 条；habit_diagnosis 最多 5 条；transfer_links 最多 5 条。
- summary 不超过 200 字，面向家长/学生可读，不出现"课标""义务教育课程标准"等术语。
- 每条 action 一句话可执行，避免空洞建议。

## 输出 schema（严格遵守，输出纯 JSON 对象）

{{
  "student_id": "{student_id}",
  "subject_pair": ["{subject_a}", "{subject_b}"],
  "transfer_links": [
    {{"subject_a_kp": "...", "subject_b_kp": "...", "evidence_curriculum_ids": ["..."], "evidence_question_ids": {{"{subject_a}": ["..."], "{subject_b}": ["..."]}}, "explanation": "..."}}
  ],
  "habit_diagnosis": [
    {{"pattern": "...", "subjects": ["{subject_a}", "{subject_b}"], "evidence_question_ids": {{"{subject_a}": ["..."], "{subject_b}": ["..."]}}, "comment": "..."}}
  ],
  "priority": [
    {{"rank": 1, "subject": "{subject_a}|{subject_b}", "knowledge_point": "...", "evidence_curriculum_ids": ["..."], "action": "...", "reason": "..."}}
  ],
  "summary": "面向家长/学生的综合诊断段落（≤200 字）"
}}'''


def _slim_memory_for_pass3(memory: Dict[str, Any]) -> Dict[str, Any]:
    slim_errors = [
        {k: q[k] for k in ('page', 'id', 'verdict', 'stem_excerpt', 'student_answer',
                           'correct_answer', 'error_type', 'knowledge_point') if k in q}
        for q in memory.get('error_questions', [])
    ]
    return {
        'subject': memory.get('subject'),
        'sample_id': memory.get('sample_id'),
        'question_count': memory.get('question_count'),
        'accuracy_overall': (memory.get('accuracy') or {}).get('overall'),
        'verdict_distribution': memory.get('verdict_distribution'),
        'error_questions': slim_errors,
        'knowledge_point_frequency': memory.get('knowledge_point_frequency'),
        'error_type_distribution': memory.get('error_type_distribution'),
    }


def _slim_report_for_pass3(report: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'subject': report.get('subject'),
        'sample_id': report.get('sample_id'),
        'diagnosis': report.get('diagnosis'),
        'zone_classification': report.get('zone_classification'),
    }


def pass3_system(subject_a: str, subject_b: str, student_id: str,
                 memory_a: Optional[Dict[str, Any]] = None, memory_b: Optional[Dict[str, Any]] = None) -> str:
    entries_a = _filter_curriculum_by_memory(load_curriculum_entries(subject_a), memory_a)
    entries_b = _filter_curriculum_by_memory(load_curriculum_entries(subject_b), memory_b)
    return PASS3_SYSTEM_BASE.format(
        student_id=student_id, subject_a=subject_a, subject_b=subject_b,
        kp_count_a=len(entries_a), kp_count_b=len(entries_b),
        curriculum_block_a=_format_curriculum_block(entries_a) or '(无)',
        curriculum_block_b=_format_curriculum_block(entries_b) or '(无)',
        zone_table=_format_zone_table(),
    )


def pass3_user(memory_a: Dict[str, Any], memory_b: Dict[str, Any],
               report_a: Dict[str, Any], report_b: Dict[str, Any]) -> str:
    payload = {
        'subject_a': {'memory': _slim_memory_for_pass3(memory_a), 'pass2_report': _slim_report_for_pass3(report_a)},
        'subject_b': {'memory': _slim_memory_for_pass3(memory_b), 'pass2_report': _slim_report_for_pass3(report_b)},
    }
    return (
        '以下是该学生两份不同学科作业的批改记忆与三区报告，'
        '请按照系统提示中的 schema 输出 JSON 跨学科分析报告。\n\n'
        + json.dumps(payload, ensure_ascii=False)
    )


def _collect_valid_qids(memory: Dict[str, Any]) -> set:
    ids: set = set()
    for q in memory.get('error_questions', []):
        if q.get('qid_global'):
            ids.add(q['qid_global'])
        if q.get('id') is not None:
            ids.add(str(q['id']))
    return ids


def _validate(result: Dict[str, Any], memory_a: Optional[Dict[str, Any]] = None,
              memory_b: Optional[Dict[str, Any]] = None,
              subject_a: str = '', subject_b: str = '') -> None:
    if not isinstance(result, dict):
        raise ValueError('Pass3 返回不是 JSON 对象')
    for key in ('transfer_links', 'habit_diagnosis', 'priority', 'summary'):
        if key not in result:
            raise ValueError(f'Pass3 返回缺少 {key}')
    if memory_a is None or memory_b is None:
        return
    valid_ids = {subject_a: _collect_valid_qids(memory_a), subject_b: _collect_valid_qids(memory_b)}
    import logging
    logger = logging.getLogger(__name__)
    for link in result.get('transfer_links') or []:
        for subj, ids in (link.get('evidence_question_ids') or {}).items():
            for qid in ids or []:
                if subj in valid_ids and qid not in valid_ids[subj]:
                    logger.warning('transfer_links: %s question id %r not in %s error_questions', subj, qid, subj)
    for diag in result.get('habit_diagnosis') or []:
        for subj, ids in (diag.get('evidence_question_ids') or {}).items():
            for qid in ids or []:
                if subj in valid_ids and qid not in valid_ids[subj]:
                    logger.warning('habit_diagnosis: %s question id %r not in %s error_questions', subj, qid, subj)


def render_summary_md(result: Dict[str, Any], subject_a: str, subject_b: str) -> str:
    la = SUBJECT_LABELS.get(subject_a, subject_a)
    lb = SUBJECT_LABELS.get(subject_b, subject_b)
    lines: List[str] = [
        f'# 双科交叉诊断报告（学生 {result.get("student_id", "?")}）', '',
        f'**学科对**：{la} × {lb}', '',
        '## 综合诊断', '', result.get('summary', '(无)'), '',
    ]
    priority = result.get('priority') or []
    lines += ['## 优先建议（最多 3 条）', '']
    lines += ['| 优先级 | 学科 | 知识点 | 建议行动 | 理由 |', '|---|---|---|---|---|']
    for p in sorted(priority, key=lambda x: x.get('rank', 99)):
        subj_label = SUBJECT_LABELS.get(p.get('subject', ''), p.get('subject', ''))
        lines.append(f"| {p.get('rank','')} | {subj_label} | {p.get('knowledge_point','')} | {p.get('action','')} | {p.get('reason','')} |")
    lines.append('')
    links = result.get('transfer_links') or []
    lines += ['## 跨学科迁移识别', '']
    if not links:
        lines.append('（未识别出显著迁移关联）')
    else:
        for lk in links:
            lines.append(f"- **{lk.get('subject_a_kp','')}** ⇄ **{lk.get('subject_b_kp','')}**：{lk.get('explanation','')}")
    lines.append('')
    habits = result.get('habit_diagnosis') or []
    lines += ['## 共性学习习惯诊断', '']
    if not habits:
        lines.append('（未发现显著共性模式）')
    else:
        for h in habits:
            lines.append(f"- **{h.get('pattern','')}**：{h.get('comment','')}")
    lines.append('')
    return '\n'.join(lines)


def cross_subject_analyze(student_id: str, subject_a: str, subject_b: str,
                          memory_a: Dict[str, Any], memory_b: Dict[str, Any],
                          report_a: Dict[str, Any], report_b: Dict[str, Any],
                          out_dir: str) -> Dict[str, Any]:
    """执行双科交叉分析，落盘 cross_subject_report.json + summary.md + thinking.txt。"""
    os.makedirs(out_dir, exist_ok=True)
    client = _deepseek_client()
    base_messages = [
        {'role': 'system', 'content': pass3_system(subject_a, subject_b, student_id, memory_a, memory_b)},
        {'role': 'user', 'content': pass3_user(memory_a, memory_b, report_a, report_b)},
    ]
    kwargs = {
        'model': homework_deepseek_model(),
        'max_tokens': 32768,
        'response_format': {'type': 'json_object'},
        'extra_body': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
    }
    report_path = os.path.join(out_dir, 'cross_subject_report.json')
    summary_path = os.path.join(out_dir, 'summary.md')
    thinking_path = os.path.join(out_dir, 'cross_subject_report.thinking.txt')

    last_raw = ''
    last_error: Optional[Exception] = None
    for attempt in range(2):
        messages = list(base_messages)
        if attempt == 1:
            messages += [
                {'role': 'assistant', 'content': last_raw},
                {'role': 'user', 'content': f'上次返回不是合法 JSON（{last_error}），请只输出一个可被 json.loads 解析的 JSON 对象。'},
            ]
        response = client.chat.completions.create(messages=messages, **kwargs)
        message = response.choices[0].message
        reasoning = getattr(message, 'reasoning_content', None) or ''
        if reasoning:
            with open(thinking_path, 'w', encoding='utf-8') as f:
                f.write(reasoning)
        last_raw = message.content or ''
        try:
            result = _loads_json_with_retry_text(last_raw)
            _validate(result, memory_a, memory_b, subject_a, subject_b)
            result.setdefault('student_id', student_id)
            result.setdefault('subject_pair', [subject_a, subject_b])
            safe_json_dump(report_path, result)
            with open(summary_path, 'w', encoding='utf-8') as f:
                f.write(render_summary_md(result, subject_a, subject_b))
            return result
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc

    error_path = os.path.join(out_dir, 'cross_subject_report.error.txt')
    with open(error_path, 'w', encoding='utf-8') as f:
        f.write(last_raw)
    raise ValueError(f'Pass3 返回不是合法 JSON，原始返回已保存到 {error_path}: {last_error}')
