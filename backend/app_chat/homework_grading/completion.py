"""批改交付摘要：执行终止、报告可用、完整交付分别判定，不启动计算。"""

RECOVERABLE = frozenset({'failed', 'interrupted', 'prepared', 'running'})
POLICY_SKIPS = frozenset({'no_wrong_verdict', 'no_high_risk_verdict',
                          'known_self_review_false_positive_allowlist'})
STAGES = ('layout', 'understanding', 'grading')


def material_evidence_summary(pages):
    """仅将明确的评价阻断列为缺项；普通uncertain不自动判失败。"""
    blockers = []
    for page in pages:
        for unit in page.get('questions', []):
            check = unit.get('material_check') or {}
            if check.get('blocks_assessment') is True:
                blockers.append({'page': page.get('page'), 'id': unit.get('id'),
                                 'reason': str(check.get('reason') or '材料依据尚未确认')[:200]})
    return {'status': 'incomplete' if blockers else 'passed', 'blockers': blockers}


def final_material_evidence(paths):
    from .utils import sorted_json_pages, safe_json_load
    return material_evidence_summary([safe_json_load(p) for p in sorted_json_pages(paths['pass1_json'])])


def review_failure_message(review):
    labels = {'queue': '等待模型调用槽位超时', 'request': '等待模型响应超时',
              'stage': '复核阶段时间预算已用尽', 'task': '整份任务时间预算已用尽',
              'cancelled': '因阶段中断未完成复核'}
    messages = []
    for item in review.get('failures') or []:
        budget = item.get('budget') or {}
        scope, page = budget.get('scope'), item.get('page')
        if scope in labels and type(page) is int:
            message = f'第{page}页{labels[scope]}'
            limit = budget.get('queue_timeout_seconds' if scope == 'queue' else 'request_timeout_seconds')
            if scope in ('queue', 'request') and isinstance(limit, (float, int)):
                message += f'（上限{limit:g}秒）'
            messages.append(message)
    return ('；'.join(messages) + '，请通过迭代补做。' if messages else
            '部分页面复核失败或未执行，请通过迭代补做。')


def review_coverage(expected_pages, details):
    """沿用既有选页策略；缺图、配额跳过和无结果不能记为成功免检。"""
    expected = sorted(set(expected_pages))
    accounted, failed, skipped = set(), set(), set()
    for item in details:
        page = item.get('page')
        if page not in expected:
            continue
        if item.get('error') or item.get('quota_limited'):
            failed.add(page)
        elif item.get('skipped'):
            if item.get('skip_reason') in POLICY_SKIPS:
                accounted.add(page)
                skipped.add(page)
            else:
                failed.add(page)
        else:
            accounted.add(page)
    missing = set(expected) - accounted
    return {'expected_pages': expected, 'completed_pages': sorted(accounted - failed),
            'policy_skipped_pages': sorted(skipped - failed),
            'incomplete_pages': sorted(missing | failed)}


def summarize_completion(manifest, report=None, *, artifacts_valid=None):
    """只读取事实字段；不相信可能从旧运行复制来的 completion 摘要。"""
    target = manifest.get('target_stage') or 'grading'
    target = target if target in STAGES else 'grading'
    stages = manifest.get('stages') or {}
    issues = []

    def add(stage, code, message):
        if not any(x['code'] == code for x in issues):
            issues.append({'stage': stage, 'code': code, 'message': message})

    status = manifest.get('status')
    running = status in ('registered', 'prepared', 'running') and manifest.get('processing_stage') != 'completed'
    if status in ('failed', 'interrupted'):
        add(manifest.get('failure_stage') or 'execution', 'execution_incomplete',
            '执行已中断，已保存的结果保留，可检查后继续处理。')
    if not running and target in stages and stages.get(target) != 'done':
        add(target, 'target_incomplete', '本次目标阶段尚未完成。')
    if artifacts_valid is False:
        add(target, 'artifacts_unverified', '批改产物或原回执暂无法核验，不能确认结果完整。')

    validation = manifest.get('content_validation') or {}
    report_validation = (report or {}).get('content_validation') or {}
    review = manifest.get('pass1_review') or {}
    final_review = manifest.get('hallucination') or {}
    if target == 'grading':
        if (manifest.get('material_evidence') or {}).get('status') == 'incomplete':
            add('review', 'material_evidence_incomplete', '部分材料依据尚未完成核验，已保留可查看结果。')
        if any(u.get('status') != 'completed' for u in review.get('required_units', [])):
            add('review', 'required_evidence_incomplete', '必要证据尚未完成复核，请通过迭代补齐。')
        if review.get('enabled') is False:
            add('review', 'review_disabled', '逐页复核未开启，不能确认完整复核已完成。')
        if review.get('errors') or review.get('quota_limited') or (review.get('coverage') or {}).get('incomplete_pages'):
            add('review', 'review_incomplete', review_failure_message(review))
        if final_review.get('status') in ('failed', 'error', 'inconclusive') or validation.get('failed_checks'):
            add('hallucination', 'final_review_incomplete', '最终批改复核未完成，请通过迭代补做。')
        if validation.get('status') == 'needs_review' or report_validation.get('status') == 'needs_review':
            add('report', 'feedback_needs_review', '部分批语尚未通过核验，已保留有效内容。')
        if (manifest.get('red_blue_review') or {}).get('status') != 'ready':
            add('quality', 'quality_incomplete', '质量评分尚未完成，可在报告复核通过后单独补做。')

    output = manifest.get('output_validation') or {}
    documented = output.get('status') == 'passed' and output.get('target_stage') == target
    if target == 'grading' and documented:
        if 'coverage' not in review:
            add('review', 'review_coverage_missing', '本轮未记录完整逐页复核覆盖情况。')
        if final_review.get('status') not in ('ready', 'passed', 'completed'):
            add('hallucination', 'final_review_incomplete', '本轮最终复核尚未确认成功。')
    core_issues = [x for x in issues if x['stage'] != 'quality']
    # 旧产物缺审核记录时仍可查看，但不能凭“有报告”开放新的评分操作。
    review_known = (review.get('enabled') is True and 'errors' in review
                    and final_review.get('status') in ('ready', 'passed', 'completed'))
    report_usable = bool(target == 'grading' and not running and stages.get('grading') == 'done'
                         and not core_issues and review_known)
    state = 'running' if running else 'incomplete' if issues else 'complete' if documented else 'unverified'
    if state == 'running':
        message = '批改任务正在执行。'
    elif state == 'unverified':
        message = '历史版本未记录完整性核验，可查看原结果。'
    elif state == 'complete':
        message = {'layout': '本次版面处理已完成。', 'understanding': '本次理解处理已完成。',
                   'grading': '本次批改流程已完成。'}[target]
    elif report_usable:
        message = '批改结果可用，质量评分待补。'
    else:
        message = '本次处理尚有未完成项，已保留已有结果。'
    return {'status': state, 'target_stage': target, 'report_usable': report_usable,
            'issues': issues, 'message': message}


def finish_delivery(manifest, report=None):
    """仅由写入流程调用；读取历史不回填。版面/理解仍保留partial兼容。"""
    manifest['processing_stage'] = 'completed'
    manifest['status'] = 'partial'
    if (manifest.get('red_blue_review') or {}).get('status') == 'ready':
        manifest['warnings'] = [w for w in manifest.get('warnings', []) if w !=
                                '批改结果已保留，但质量评分未成功；可在结果中单独重试评分']
    completion = summarize_completion(manifest, report)
    manifest['completion'] = completion
    if completion['target_stage'] == 'grading' and completion['status'] == 'complete':
        manifest['status'] = 'completed'
    return completion


def available_actions(manifest, completion, *, snapshot_ok, current=True, task=None,
                      artifacts_ok=False, task_error=''):
    busy = bool(task and not task.get('completed')) or completion['status'] == 'running'
    blocked = ('历史版本仅供查看，请切回当前版本。' if not current else
               task_error or ('本材料任务仍在执行。' if busy else ''))
    incremental_block = blocked or ('' if snapshot_ok else '原快照无法恢复，请明确选择完整新算。')
    session = manifest.get('session_rerun') or {}
    resumable = (manifest.get('status') in RECOVERABLE or bool(session.get('resume_available')))
    resume_block = incremental_block or ('' if resumable else '当前没有可继续的中断任务。')
    quality_block = incremental_block or ('' if completion['report_usable'] else '请先通过迭代补齐批改复核。')
    quality_block = quality_block or ('' if artifacts_ok else '原批改产物或回执无法核验，暂不能单独评分。')
    if (manifest.get('red_blue_review') or {}).get('status') == 'ready':
        quality_block = quality_block or '当前卡标已完成。'
    return {
        'resume': {'enabled': not resume_block, 'reason': resume_block,
                   'rerun_stage': session.get('rerun_stage') if session.get('resume_available') else completion['target_stage']},
        'rerun_grading': {'enabled': not incremental_block, 'reason': incremental_block},
        'retry_quality': {'enabled': not quality_block, 'reason': quality_block},
    }


def saved_report_ready(paths, manifest):
    """补评分核验保存时的回执和当前文件；不拿新上游代码哈希使旧报告失效。"""
    from .artifact_transaction import transaction_pending
    from .execution_checkpoints import receipt_matches
    from .feedback_artifacts import validate_artifacts
    from .staged_pipeline import load_homework_clean_pages
    if transaction_pending(paths['base']) or not summarize_completion(manifest)['report_usable']:
        return False
    receipt = (manifest.get('stage_receipts') or {}).get('grading') or {}
    if not receipt.get('code'):
        return False
    try:
        if final_material_evidence(paths)['status'] == 'incomplete':
            return False
        if not receipt_matches(paths, manifest, 'grading', code={'actual_code_fingerprint': receipt['code']}):
            return False
        if receipt.get('schema') == 3:
            rendering = (manifest.get('stage_receipts') or {}).get('render') or {}
            if not rendering.get('code') or not receipt_matches(paths, manifest, 'render',
                    code={'actual_code_fingerprint': rendering['code']}):
                return False
        validate_artifacts(paths, load_homework_clean_pages(paths), manifest, 'grading',
                           expected_pages=manifest.get('source_page_count'))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
