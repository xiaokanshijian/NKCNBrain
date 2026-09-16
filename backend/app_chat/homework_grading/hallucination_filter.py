"""L4 二级筛分 · 统一幻觉过滤（飞沙堰，nkcn 自有，改编自 yq v2.0）。

校验 Pass1 / Pass2 输出中的幻觉风险：
1. invalid_kp        ：knowledge_point 不在课标标签白名单
2. invalid_id        ：Pass2 evidence_question_ids 引用不存在的题号
3. invalid_curr_id   ：evidence_curriculum_ids 不在课标 JSON
4. unfounded_citation：批语引用书名号内容但课标中找不到依据

默认仅打标记并产出 hallucination_report.json（retry 默认关闭）。
"""

from __future__ import annotations

from .feedback_runtime import stamp_feedback
from .feedback_curriculum import curriculum_entries
from .feedback_verification import validate_page

import difflib
import json
import logging
import os
import re
import shutil
from typing import Any, Dict, List, Optional, Set

from app_chat.homework_grading.curriculum import curriculum_index
from app_chat.homework_grading.semantic_config import get_seed_labels
from app_chat.homework_grading.utils import safe_json_dump, safe_json_load, sorted_json_pages, evidence_values, normalize_question_evidence

logger = logging.getLogger(__name__)

_CITE_RE = re.compile(r'《([^》]{2,40})》|「([^」]{2,40})」')


def _fuzzy(value: str, valid: Set[str], cutoff: float = 0.7) -> str | None:
    matches = difflib.get_close_matches(value, list(valid), n=1, cutoff=cutoff)
    return matches[0] if matches else None


def _collect_question_ids(pass1_dir: str) -> Set[str]:
    ids: Set[str] = set()
    for json_path in sorted_json_pages(pass1_dir):
        name = os.path.basename(json_path)
        if '.error' in name or '_no_thinking' in name:
            continue
        try:
            data = safe_json_load(json_path)
        except Exception:
            continue
        for q in data.get('questions') or []:
            if q.get('id'):
                qid = str(q['id'])
                page_num = data.get('page')
                if page_num is not None:
                    ids.add(f'p{page_num}:{qid}')
    return ids


def _filter_pass1(
    pass1_dir: str,
    seed_labels: Set[str],
    page_nums: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for json_path in sorted_json_pages(pass1_dir):
        name = os.path.basename(json_path)
        if '.error' in name or '_no_thinking' in name:
            continue
        try:
            data = safe_json_load(json_path)
        except Exception:
            continue
        page = data.get('page')
        if page_nums is not None:
            try:
                if int(page) not in page_nums:
                    continue
            except (TypeError, ValueError):
                continue
        for q in data.get('questions') or []:
            kp = q.get('knowledge_point')
            if not kp or kp in seed_labels:
                continue
            issues.append({
                'source': 'pass1', 'page': page, 'question_id': q.get('id'),
                'field': 'knowledge_point', 'value': kp,
                'hallucination_type': 'invalid_kp', 'suggestion': _fuzzy(kp, seed_labels),
            })
    return issues


def _extract_citations(text: str) -> List[str]:
    out = []
    for m in _CITE_RE.finditer(text or ''):
        v = m.group(1) or m.group(2)
        if v:
            out.append(v.strip())
    return out


def _citation_supported(cite: str, descriptions: List[str]) -> bool:
    if not cite:
        return True
    for desc in descriptions:
        if cite in desc:
            return True
    return bool(difflib.get_close_matches(cite, descriptions, n=1, cutoff=0.6))


def _filter_pass2(report_path: str, valid_qids: Set[str], seed_labels: Set[str],
                  valid_curr_ids: Set[str], descriptions: List[str]) -> List[Dict[str, Any]]:
    if not os.path.exists(report_path):
        return []
    try:
        report = safe_json_load(report_path)
    except Exception as exc:
        logger.warning('无法解析 pass2 报告：%s', exc)
        return []
    issues: List[Dict[str, Any]] = []
    zc = report.get('zone_classification') or {}
    if not isinstance(zc, dict):
        return issues
    for zone, items in zc.items():
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            ctx = {'zone': zone, 'index': idx}
            kp = item.get('knowledge_point')
            if kp and kp not in seed_labels:
                issues.append({'source': 'pass2', **ctx, 'field': 'knowledge_point', 'value': kp,
                               'hallucination_type': 'invalid_kp', 'suggestion': _fuzzy(kp, seed_labels)})
            for qid in evidence_values(item.get('evidence_question_ids')):
                if str(qid) not in valid_qids:
                    issues.append({'source': 'pass2', **ctx, 'field': 'evidence_question_ids', 'value': qid,
                                   'hallucination_type': 'invalid_id', 'suggestion': None})
            for cid in evidence_values(item.get('evidence_curriculum_ids')):
                if cid not in valid_curr_ids:
                    issues.append({'source': 'pass2', **ctx, 'field': 'evidence_curriculum_ids', 'value': cid,
                                   'hallucination_type': 'invalid_curr_id', 'suggestion': _fuzzy(cid, valid_curr_ids)})
            for cite in _extract_citations(item.get('comment') or ''):
                if not _citation_supported(cite, descriptions):
                    issues.append({'source': 'pass2', **ctx, 'field': 'comment_citation', 'value': cite,
                                   'hallucination_type': 'unfounded_citation', 'suggestion': None})
    return issues


def _backup_once(path: str) -> None:
    bak = path + '.corrected.bak'
    if os.path.exists(path) and not os.path.exists(bak):
        try:
            shutil.copyfile(path, bak)
        except Exception:
            logger.warning('hallucination backup failed: %s', bak)


def _apply_pass1_corrections(pass1_dir: str, issues: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """对 pass1 invalid_kp 命中的题目把 knowledge_point 清空（备份后写回）。"""
    applied: List[Dict[str, Any]] = []
    targets: Dict[Any, Set[str]] = {}
    for issue in issues:
        if issue.get('source') != 'pass1' or issue.get('hallucination_type') != 'invalid_kp':
            continue
        targets.setdefault(issue.get('page'), set()).add(str(issue.get('question_id')))
    if not targets:
        return applied
    for json_path in sorted_json_pages(pass1_dir):
        try:
            data = safe_json_load(json_path)
        except Exception:
            continue
        page = data.get('page')
        if page not in targets:
            continue
        ids = targets[page]
        mutated = False
        for q in data.get('questions') or []:
            qid = str(q.get('id'))
            if qid in ids and q.get('knowledge_point'):
                applied.append({'source': 'pass1', 'page': page, 'question_id': qid,
                                'field': 'knowledge_point', 'before': q.get('knowledge_point'), 'after': ''})
                q['knowledge_point'] = ''
                mutated = True
        if mutated:
            _backup_once(json_path)
            safe_json_dump(json_path, data)
    return applied


def _apply_zone_corrections(zones_root: Dict[str, Any], valid_qids: Set[str], valid_curr_ids: Set[str], label_whitelist: Set[str]) -> List[Dict[str, Any]]:
    """统一处理 zone_classification（Pass2）/ zones（ontology）：清掉无效的 evidence/curriculum_id/knowledge_point。"""
    applied: List[Dict[str, Any]] = []
    if not isinstance(zones_root, dict):
        return applied
    for zone, items in list(zones_root.items()):
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            kp = item.get('knowledge_point')
            if kp and kp not in label_whitelist:
                applied.append({'zone': zone, 'index': idx, 'field': 'knowledge_point',
                                'before': kp, 'after': ''})
                item['knowledge_point'] = ''
            for field in ('evidence_question_ids', 'evidence'):
                if field not in item:
                    continue
                cleaned = normalize_question_evidence(item[field], valid_qids)
                if cleaned != item[field]:
                    applied.append({'zone': zone, 'index': idx, 'field': field,
                                    'before': item[field], 'after': cleaned})
                    item[field] = cleaned
            if 'evidence_curriculum_ids' in item:
                cleaned_c = [c for c in (item.get('evidence_curriculum_ids') or []) if c in valid_curr_ids]
                if len(cleaned_c) != len(item.get('evidence_curriculum_ids') or []):
                    applied.append({'zone': zone, 'index': idx, 'field': 'evidence_curriculum_ids',
                                    'before': item.get('evidence_curriculum_ids'), 'after': cleaned_c})
                    item['evidence_curriculum_ids'] = cleaned_c
            curr_id = item.get('curriculum_id')
            if curr_id and curr_id not in valid_curr_ids:
                applied.append({'zone': zone, 'index': idx, 'field': 'curriculum_id',
                                'before': curr_id, 'after': ''})
                item['curriculum_id'] = ''
            for ec_idx, ec in enumerate(item.get('error_clusters') or []):
                if not isinstance(ec, dict) or 'evidence' not in ec:
                    continue
                cleaned_ec = normalize_question_evidence(ec['evidence'], valid_qids)
                if cleaned_ec != ec['evidence']:
                    applied.append({'zone': zone, 'index': idx, 'field': f'error_clusters[{ec_idx}].evidence',
                                    'before': ec['evidence'], 'after': cleaned_ec})
                    ec['evidence'] = cleaned_ec
    return applied


def _apply_report_corrections(report_path: str, valid_qids: Set[str], valid_curr_ids: Set[str], label_whitelist: Set[str]) -> List[Dict[str, Any]]:
    if not os.path.exists(report_path):
        return []
    try:
        report = safe_json_load(report_path)
    except Exception:
        return []
    applied = _apply_zone_corrections(report.get('zone_classification') or {}, valid_qids, valid_curr_ids, label_whitelist)
    if applied:
        _backup_once(report_path)
        safe_json_dump(report_path, report)
    return [{'target': 'pass2_report', **a} for a in applied]


def _apply_ontology_corrections(ontology_path: str, valid_qids: Set[str], valid_curr_ids: Set[str], label_whitelist: Set[str]) -> List[Dict[str, Any]]:
    if not os.path.exists(ontology_path):
        return []
    try:
        ontology = safe_json_load(ontology_path)
    except Exception:
        return []
    applied = _apply_zone_corrections(ontology.get('zones') or {}, valid_qids, valid_curr_ids, label_whitelist)
    if applied:
        _backup_once(ontology_path)
        safe_json_dump(ontology_path, ontology)
    return [{'target': 'student_ontology', **a} for a in applied]


_ONTOLOGY_PLACEHOLDER_FALLBACKS = frozenset({'no_observed', 'generic_extension'})


def _filter_ontology(ontology_path: str, valid_qids: Set[str], label_whitelist: Set[str], valid_curr_ids: Set[str]) -> List[Dict[str, Any]]:
    """校验 student_ontology.json 中的 zones 幻觉（invalid_kp / invalid_id / invalid_curr_id）。"""
    if not ontology_path or not os.path.exists(ontology_path):
        return []
    try:
        ontology = safe_json_load(ontology_path)
    except Exception as exc:
        logger.warning('无法解析 ontology：%s', exc)
        return []
    issues: List[Dict[str, Any]] = []
    zones = ontology.get('zones') or {}
    if not isinstance(zones, dict):
        return issues
    for bucket, items in zones.items():
        if not isinstance(items, list):
            continue
        for idx, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            fallback = item.get('fallback') or item.get('reason') or ''
            if fallback in _ONTOLOGY_PLACEHOLDER_FALLBACKS:
                continue
            ctx = {'source': 'ontology', 'zone': bucket, 'index': idx}
            kp = item.get('knowledge_point')
            if kp and kp not in label_whitelist:
                issues.append({**ctx, 'field': 'knowledge_point', 'value': kp,
                               'hallucination_type': 'invalid_kp', 'suggestion': _fuzzy(kp, label_whitelist)})
            curr_id = item.get('curriculum_id')
            if curr_id and curr_id not in valid_curr_ids:
                issues.append({**ctx, 'field': 'curriculum_id', 'value': curr_id,
                               'hallucination_type': 'invalid_curr_id', 'suggestion': _fuzzy(curr_id, valid_curr_ids)})
            for qid in evidence_values(item.get('evidence')):
                if str(qid) not in valid_qids:
                    issues.append({**ctx, 'field': 'evidence', 'value': qid,
                                  'hallucination_type': 'invalid_id', 'suggestion': None})
            for ec_idx, ec in enumerate(item.get('error_clusters') or []):
                if not isinstance(ec, dict):
                    continue
                for qid in evidence_values(ec.get('evidence')):
                    if str(qid) not in valid_qids:
                        issues.append({**ctx, 'field': f'error_clusters[{ec_idx}].evidence', 'value': qid,
                                      'hallucination_type': 'invalid_id', 'suggestion': None})
    return issues


def _issue_key(issue: Dict[str, Any]) -> tuple:
    return (issue.get('source'), issue.get('page'), issue.get('question_id'),
            issue.get('zone'), issue.get('index'), issue.get('field'))


def _build_retry_prompt(issue: Dict[str, Any], label_whitelist: Set[str],
                        valid_qids: Set[str], valid_curr_ids: Set[str]) -> Optional[str]:
    htype = issue.get('hallucination_type')
    val = issue.get('value', '')
    if htype == 'invalid_kp':
        candidates = sorted(label_whitelist)[:30]
        return (f'以下知识点标签 "{val}" 不在课标白名单中。'
                f'请从下列合法标签中选出最相近的一个，只输出标签字符串，不附任何解释：\n'
                + ', '.join(candidates))
    if htype == 'invalid_id':
        candidates = sorted(valid_qids)[:30]
        return (f'题号引用 "{val}" 不存在。'
                f'请从下列合法题号中选出最相近的一个，只输出题号字符串，不附任何解释：\n'
                + ', '.join(candidates))
    if htype == 'invalid_curr_id':
        candidates = sorted(valid_curr_ids)[:30]
        return (f'课标条目 ID "{val}" 不存在。'
                f'请从下列合法课标 ID 中选出最相近的一个，只输出 ID 字符串，不附任何解释：\n'
                + ', '.join(candidates))
    return None


def _call_retry(prompt: str, *, feedback_runtime=None) -> str:
    if feedback_runtime is not None:
        from .feedback_prompts import context_block, reference_block
        prompt = context_block(feedback_runtime) + reference_block(feedback_runtime) + prompt
    try:
        from app_chat.homework_grading.llm_clients import _deepseek_client, homework_deepseek_model  # lazy import
        client = _deepseek_client()
        from .feedback_model import runtime_client
        client = runtime_client(client, feedback_runtime, "deepseek")
        resp = client.chat.completions.create(
            model=homework_deepseek_model(),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=64,
            temperature=0.0,
            extra_body={'thinking': {'type': 'disabled'}},
        )
        return (resp.choices[0].message.content or '').strip()
    except Exception as exc:
        logger.debug('hallucination retry LLM call failed: %s', exc)
        return ''


def retry_field(issue: Dict[str, Any], label_whitelist: Set[str],
                valid_qids: Set[str], valid_curr_ids: Set[str],
                max_attempts: int = 2, *, feedback_runtime=None) -> Dict[str, Any]:
    if feedback_runtime is not None and issue.get('hallucination_type') in ('invalid_id', 'invalid_curr_id'):
        return {'field': issue.get('field'), 'old_value': issue.get('value'), 'new_value': None, 'attempts': 0, 'reason': '缺少可证明替代关系的证据，不按字符串相似度猜测引用'}
    prompt = _build_retry_prompt(issue, label_whitelist, valid_qids, valid_curr_ids)
    if not prompt:
        return {'field': issue.get('field'), 'old_value': issue.get('value'), 'new_value': None, 'attempts': 0}
    htype = issue.get('hallucination_type')
    valid_set = (label_whitelist if htype == 'invalid_kp'
                 else valid_qids if htype == 'invalid_id'
                 else valid_curr_ids)
    for attempt in range(1, max_attempts + 1):
        candidate = _call_retry(prompt, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
        if candidate and candidate in valid_set:
            return {'field': issue.get('field'), 'old_value': issue.get('value'),
                    'new_value': candidate, 'attempts': attempt}
    return {'field': issue.get('field'), 'old_value': issue.get('value'), 'new_value': None, 'attempts': max_attempts}


def _pre_patch_with_retry(pass1_dir: str, report_path: str, ontology_path: Optional[str],
                          retry_map: Dict[tuple, str], all_issues: List[Dict[str, Any]],
                          applied_out: List[Dict[str, Any]]) -> None:
    """Patch Pass1/Pass2/Ontology JSON files with retry-suggested values (pre-pass before clear-pass)."""
    for issue in all_issues:
        key = _issue_key(issue)
        new_val = retry_map.get(key)
        if new_val is None:
            continue
        source = issue.get('source')
        field = issue.get('field')
        if source == 'pass1':
            for json_path in sorted_json_pages(pass1_dir):
                try:
                    data = safe_json_load(json_path)
                except Exception:
                    continue
                if data.get('page') != issue.get('page'):
                    continue
                for q in data.get('questions') or []:
                    if str(q.get('id')) == str(issue.get('question_id')) and q.get(field):
                        _backup_once(json_path)
                        applied_out.append({'target': 'pass1_json', 'source': 'retry',
                                            'page': issue.get('page'), 'question_id': issue.get('question_id'),
                                            'field': field, 'before': q[field], 'after': new_val})
                        q[field] = new_val
                        safe_json_dump(json_path, data)
                        break
        elif source in ('pass2', 'ontology'):
            target_path = report_path if source == 'pass2' else (ontology_path or '')
            if not target_path or not os.path.exists(target_path):
                continue
            try:
                doc = safe_json_load(target_path)
            except Exception:
                continue
            zone_key = 'zone_classification' if source == 'pass2' else 'zones'
            zones = doc.get(zone_key) or {}
            bucket = issue.get('zone')
            idx = issue.get('index')
            items = zones.get(bucket) if isinstance(zones, dict) else None
            if not isinstance(items, list) or idx is None or idx >= len(items):
                continue
            item = items[idx]
            if not isinstance(item, dict) or not item.get(field):
                continue
            if field in ('evidence', 'evidence_question_ids', 'evidence_curriculum_ids'):
                # retry仅修复被报告的成员，不能将整个证据数组覆盖为字符串。
                before = item[field]
                if not isinstance(before, list) or issue.get('value') not in before:
                    continue
                new_val = [new_val if value == issue['value'] else value for value in before]
            _backup_once(target_path)
            applied_out.append({'target': f'{source}_json', 'source': 'retry',
                                 'zone': bucket, 'index': idx,
                                 'field': field, 'before': item[field], 'after': new_val})
            item[field] = new_val
            safe_json_dump(target_path, doc)


def run_hallucination_filter(
    subject: str,
    pass1_dir: str,
    report_path: str,
    out_report_path: str,
    ontology_path: Optional[str] = None,
    stage: int = 2,
    page_nums: Optional[Set[int]] = None,
*, feedback_runtime=None) -> Dict[str, Any]:
    """对 Pass1/Pass2/Ontology 输出做幻觉过滤，落盘 hallucination_report.json + corrections_applied.json，并三件套 patch 原文件（带 .corrected.bak）。"""
    if feedback_runtime is not None:
        subject = feedback_runtime.context['subject_code']
    if feedback_runtime is None:
        seed = set(get_seed_labels(subject, stage=stage))
        curr_ids, curr_labels, descriptions = curriculum_index(subject, stage=stage)
        label_whitelist = seed | curr_labels
    else:
        entries = curriculum_entries(feedback_runtime)
        curr_ids = {e['id'] for e in entries}
        descriptions = [e.get('description', '') for e in entries]
        refs = feedback_runtime.dependencies['references']
        descriptions += [refs['reference_text']] + [d['content'] for d in refs['documents']]
        label_whitelist = {e['label'] for e in entries} | {'no_observed'}
        for path in sorted_json_pages(pass1_dir):
            data = safe_json_load(path)
            validate_page(data, feedback_runtime)
            label_whitelist.update(q['knowledge_point'] for q in data['questions'] if q.get('knowledge_point'))
        for path in (report_path, ontology_path):
            if path:
                doc = safe_json_load(path)
                if doc.get('feedback_execution', {}).get('config_fingerprint') != feedback_runtime.fingerprint:
                    raise ValueError('过滤输入与本轮配置不一致')
    valid_qids = _collect_question_ids(pass1_dir)

    pass1_issues = _filter_pass1(pass1_dir, label_whitelist, page_nums=page_nums)
    pass2_issues = _filter_pass2(report_path, valid_qids, label_whitelist, curr_ids, descriptions)
    ontology_issues: List[Dict[str, Any]] = []
    if ontology_path and os.path.exists(ontology_path):
        ontology_issues = _filter_ontology(ontology_path, valid_qids, label_whitelist, curr_ids)
    all_issues = pass1_issues + pass2_issues + ontology_issues

    type_counts: Dict[str, int] = {}
    for issue in all_issues:
        t = issue.get('hallucination_type', 'unknown')
        type_counts[t] = type_counts.get(t, 0) + 1

    corrections_applied: List[Dict[str, Any]] = []

    # ── Fix-5 LLM retry：对 invalid_kp/invalid_id/invalid_curr_id 尝试替换为合法值 ──
    retry_map: Dict[tuple, str] = {}
    try:
        retryable = [i for i in all_issues
                     if i.get('hallucination_type') in ('invalid_kp', 'invalid_id', 'invalid_curr_id')]
        for issue in retryable:
            r = retry_field(issue, label_whitelist=label_whitelist,
                            valid_qids=valid_qids, valid_curr_ids=curr_ids, **({"feedback_runtime": feedback_runtime} if feedback_runtime is not None else {}))
            if r.get('new_value') is not None:
                retry_map[_issue_key(issue)] = r['new_value']
        if retry_map:
            _pre_patch_with_retry(pass1_dir, report_path, ontology_path, retry_map,
                                  all_issues, corrections_applied)
    except Exception as exc:
        logger.warning('幻觉 retry 失败，回退清空策略：%s', exc)

    corrections_applied += [{'target': 'pass1_json', **c} for c in _apply_pass1_corrections(pass1_dir, pass1_issues)]
    corrections_applied += _apply_report_corrections(report_path, valid_qids, curr_ids, label_whitelist)
    if ontology_path:
        corrections_applied += _apply_ontology_corrections(ontology_path, valid_qids, curr_ids, label_whitelist)

    report = {
        'subject': subject,
        'total_issues': len(all_issues),
        'pass1_issue_count': len(pass1_issues),
        'pass2_issue_count': len(pass2_issues),
        'ontology_issue_count': len(ontology_issues),
        'type_counts': type_counts,
        'issues': all_issues,
        'corrections_applied_count': len(corrections_applied),
    }
    safe_json_dump(out_report_path, stamp_feedback(report, feedback_runtime, 'filter'))

    if corrections_applied:
        applied_path = os.path.join(os.path.dirname(out_report_path), 'corrections_applied.json')
        safe_json_dump(applied_path, {
            'subject': subject,
            'count': len(corrections_applied),
            'applied': corrections_applied,
        })

    logger.info('L4 幻觉过滤：%d 处风险（%s），%d 处已修正', len(all_issues), type_counts, len(corrections_applied))
    return report
