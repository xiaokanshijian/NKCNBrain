"""P02受控校验调度；无专项仍执行结构/证据与资料不足检查。"""
from .stage_dependencies import artifact_compatible
import copy
import os
import shutil

from .feedback_runtime import stamp_feedback
from .utils import safe_json_load, safe_json_dump, sorted_json_pages


def validate_page(data, runtime):
    if not isinstance(data,dict) or type(data.get('page')) is not int or data['page']<1 or not isinstance(data.get('questions'),list):
        raise ValueError('题目页面结构无效')
    if not artifact_compatible(data, runtime):
        raise ValueError('题目页面配置与当前运行不一致')
    ids=set()
    for q in data['questions']:
        if not isinstance(q,dict) or not str(q.get('id') or '').strip() or str(q['id']) in ids:
            raise ValueError('题目身份缺失或重复')
        ids.add(str(q['id']))
        if q.get('qid_global') not in (None,'',f"p{data['page']}:{q['id']}"):
            raise ValueError('题目证据身份不一致')


def verify_with_runtime(subject, pass1_dir, out_report_path, *, feedback_runtime, apply=True,
                        page_nums=None, source_document_sha256='', kind='subject'):
    from . import verifiers as v
    from . import answer_statement_verifier as a
    from .rubric_verifiers import evaluate_source_lock
    runtime=feedback_runtime;subject=runtime.context['subject_code']
    selected=None if page_nums is None else set(map(int,page_nums))
    pages=[]
    for path in sorted_json_pages(pass1_dir):
        try:
            data=safe_json_load(path)
            validate_page(data,runtime)
        except ValueError as exc:
            raise ValueError(f'{os.path.basename(path)}：{exc}') from exc
        if selected is None or data['page'] in selected:pages.append((path,data))
    enabled=runtime.has_specialized(subject) and (kind!='answer_statement' or subject=='math')
    statuses=[];details=[];applied=0
    for path,data in pages:
        original=copy.deepcopy(data)
        for q in data['questions']:
            if q.get('unit_type','question')!='question':
                statuses.append({'page':data['page'],'id':q['id'],'status':'not_applicable','reason':'非题目单元不进入专项验算'})
                continue
            issue=None
            # 证据不足是公共保护，不依赖英语专项注册。
            if kind=='subject':issue=evaluate_source_lock(q)
            status='not_covered'
            if enabled:
                status='executed_no_discrepancy'
                if kind=='answer_statement':
                    applicable=q.get('is_application_major_problem') is True
                    issue=a.forbidden_final_unit_issue(q) or a.missing_answer_statement_issue(q) or a.missing_substitution_answer_unit_issue(q)
                    if not issue and not applicable:status='not_applicable'
                else:
                    if not issue and subject=='chinese' and source_document_sha256:
                        issue=v._check_fixed_chinese_sample(q,data['page'],source_document_sha256,feedback_runtime=runtime)
                    if not issue:issue=v._VERIFIERS[subject](q,data['page'])
            if enabled and kind=='subject' and subject=='english' and v._CHECKER.backend=='none':
                statuses.append({'page':data['page'],'id':q['id'],'rule':'spelling','status':'unavailable','reason':'拼写字典不可用，未执行'})
            statuses.append({'page':data['page'],'id':q['id'],'status':'discrepancy' if issue else status,
                             'reason':'未匹配专项，公共检查已执行' if not enabled else '已按原题型条件调用，未发现差异不代表题目已验算正确'})
            if not issue:continue
            details.append(dict(issue,page=data['page'],question_id=q['id'],model_verdict=q.get('verdict')))
            if apply:
                q.update(issue.get('apply_updates') or {})
                q['verdict']=issue.get('apply_verdict') or 'uncertain'
                if kind=='answer_statement':q['error_type']=q.get('error_type') or issue.get('error_type') or '缺少最终答话'
                if q['verdict']=='uncertain':q['uncertain_reason']=issue.get('uncertain_reason') or 'verifier_override'
                q['verification_result']={'rule':issue.get('rule'),'local_verdict':issue.get('local_verdict'),
                                          'applied_verdict':q['verdict'],'detail':issue.get('detail')}
                if issue.get('source_lock'):q['source_lock']=issue['source_lock']
                if issue.get('rubric_check'):q.setdefault('rubric_checks',[]).append(issue['rubric_check'])
                applied+=1
        if apply and data!=original:
            backup=path+'.corrected.bak'
            if not os.path.exists(backup):shutil.copyfile(path,backup)
            safe_json_dump(path,stamp_feedback(data,runtime,'verifier'))
    report=stamp_feedback({'subject':subject,'skipped':not enabled,'reason':'' if enabled else '专项未覆盖，公共检查仍执行',
                           'total_discrepancies':len(details),'corrections_applied':applied,'details':details,
                           'checks':statuses,'public_checks':'executed'},runtime,'verifier')
    safe_json_dump(out_report_path,report)
    return report
