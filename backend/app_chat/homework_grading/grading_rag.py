"""选中文档的批改检索。只消费当前完成版，派生索引失败不改变批改状态。"""
import copy
import hashlib
import json
import logging
import threading
from pathlib import Path

from .page_feedback import display_context

logger = logging.getLogger(__name__)
INDEX_SCHEMA = 'grading-rag-v1'
WAIT_SECONDS = 6
MAX_CHARS = 6000
_jobs = {}
_jobs_lock = threading.Lock()
_slots = threading.BoundedSemaphore(2)
GUIDANCE = ('【所选材料批改参考】以下内容是已有批改的观察和建议，不是原文事实。'
            '回答逐项注明文件名和PDF第几页，区分原文、模型理解和批改建议；'
            '待确认与非作答不能变成确定错误。没有独立时间证据，不依据文件或页码顺序推断进退步。'
            '仅使用本轮所选材料；历史对话中的其他文件或旧版批改不得作为本轮材料依据。\n')


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()


def _read(path, root):
    path, root = Path(path), Path(root).resolve()
    if path.is_symlink() or root not in path.resolve().parents:
        raise ValueError('批改产物路径无效')
    return json.loads(path.read_text(encoding='utf-8'))


def _source_hash(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _index_state(root):
    path = Path(root) / 'grading_rag_state.json'
    try:
        value = _read(path, root) if path.exists() else {}
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        # 派生状态损坏可重建；不改变作为事实来源的原批改产物。
        return {}


def inspect_file(workspace, filename, records):
    """只读检查：不创建工作区、不触发模型、不读取归档版。"""
    from django.conf import settings
    from app_chat.ci_access import assert_workspace_path
    from .homework_versions import resolve_homework_run_root
    from .feedback_snapshot_reader import read_feedback_snapshot
    from .utils import sorted_json_pages

    item = {'filename': filename, 'status': 'not_graded', 'message': '尚无当前已完成批改，使用原文。'}
    try:
        base = Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace
        source = Path(assert_workspace_path(workspace, base / filename))
        if not source.is_file():
            return {**item, 'status': 'unavailable', 'message': '原文件不存在，批改参考不可用。'}
        from app_chat.feedback_material_identity import record_digest
        source_hash = _source_hash(source)
        candidates = [r for r in records if (filename in (r.get('files') or [])
                      or record_digest(workspace, r) == source_hash)
                      and (r.get('analysis_type') == 'homework_grading'
                           or str(r.get('analysis_id', '')).startswith('homework_'))]
        if not candidates:
            return item
        record = max(candidates, key=lambda r: str(r.get('updated_at') or r.get('created_at') or ''))
        analysis_id = record['analysis_id']
        root = Path(resolve_homework_run_root(workspace, analysis_id))
        assert_workspace_path(workspace, root)
        manifest = _read(root / 'manifest.json', root)
        item.update(analysis_id=analysis_id, run_id=manifest.get('run_id') or 'legacy-current')
        from .completion import summarize_completion
        completion = summarize_completion(manifest)
        if any(issue['stage'] != 'quality' for issue in completion['issues']):
            return {**item, 'status': 'unavailable', 'message': '当前批改复核未完成，暂仅使用原文。'}
        allowed_statuses = ('completed', 'partial') if completion['report_usable'] else ('completed',)
        if (record.get('status') not in allowed_statuses or manifest.get('status') not in allowed_statuses
                or (manifest.get('stages') and manifest['stages'].get('grading') != 'done')):
            return {**item, 'status': 'unavailable', 'message': '当前批改未完成或已中断，暂仅使用原文。',
                    'version': _digest([item['run_id'], record.get('status'), manifest.get('status')])}
        if (manifest.get('username') not in (None, '', workspace)
                or (filename not in manifest.get('selected_files', [])
                    and manifest.get('source_document_sha256') != source_hash)):
            raise ValueError('批改结果与材料不对应')
        source_hash = _source_hash(source)
        expected = manifest.get('source_document_sha256')
        # 老结果若没有完整指纹，仅接受原来就采用源哈希命名的分析目录。
        if not expected:
            # Python 3.8 无 str.removeprefix
            suffix = analysis_id[9:] if analysis_id.startswith('homework_') else analysis_id
            if len(suffix) < 12 or not source_hash.startswith(suffix):
                return {**item, 'status': 'unavailable', 'message': '旧批改无法核实原文件身份，请重新批改后使用。'}
        elif expected != source_hash:
            return {**item, 'status': 'unavailable', 'message': '原文件已变化，当前批改不适用于此文件。'}
        subject = manifest.get('subject') or 'unknown'
        sample = (manifest.get('group_id') or analysis_id).replace('homework_', '')[:8]
        report = _read(root / 'homework_grading' / 'pass2_report' / f'{subject}_{sample}_report.json', root)
        if not isinstance(report, dict) or not all(k in report for k in ('diagnosis', 'zone_classification', 'per_question_feedback')):
            raise ValueError('批改报告不完整')
        pages = [_read(p, root) for p in sorted_json_pages(str(root / 'homework_grading' / 'pass1_json'))]
        if not pages:
            raise ValueError('逐页依据缺失')
        from .completion import material_evidence_summary
        if material_evidence_summary(pages)['status'] == 'incomplete':
            return {**item, 'status': 'unavailable', 'message': '材料依据尚未完成核验，暂仅使用原文。'}
        snapshot = read_feedback_snapshot(root, manifest)
        if snapshot['snapshot_status'] not in ('complete', 'legacy_missing'):
            raise ValueError('运行依据损坏')
        version = _digest([INDEX_SCHEMA, workspace, filename, item['run_id'], source_hash, report, pages,
                           snapshot.get('feedback_context')])
        state = _index_state(root)
        index_status = state.get('status', 'missing') if state.get('version') == version else 'missing'
        return {**item, 'status': 'available', 'message': '', 'version': version, 'index_status': index_status,
                '_workspace': workspace, '_root': str(root), '_manifest': manifest, '_report': report,
                '_pages': pages, '_context': snapshot.get('feedback_context'), '_source_hash': source_hash}
    except Exception as exc:
        logger.warning('批改参考检查失败：%s', type(exc).__name__)
        return {**item, 'status': 'unavailable', 'message': '批改依据暂不可用，本轮仅使用原文。'}


def inspect_selection(workspace, filenames):
    from app_chat.ci.index_manager import CIIndexManager
    try:
        # 先验证工作区，防止索引查找越界。
        from django.conf import settings
        from app_chat.ci_access import assert_workspace_path
        assert_workspace_path(workspace, Path(settings.BASE_DIR) / 'received_dir' / 'user_raw_file' / workspace)
        records = CIIndexManager.load(workspace) if filenames else []
        items = [inspect_file(workspace, name, records) for name in dict.fromkeys(filenames)]
    except Exception:
        items = [{'filename': name, 'status': 'unavailable', 'message': '批改索引暂不可用，使用原文。'}
                 for name in dict.fromkeys(filenames)]
    return {'items': items, 'cache_key': _digest([workspace, public_status(items)])}


def cache_matches(cached, selection):
    return (cached.get('grading_cache_key') == selection['cache_key'] and not any(
        s.get('status') in ('pending', 'failed') for s in cached.get('grading_context_status', [])))


def apply_reference_policy(params, statuses):
    """即使本轮没有可用批改，也明确阻止从历史对话取回旧版诊断。"""
    if not statuses or all(s.get('status') == 'not_graded' for s in statuses):
        return
    ready = [s['filename'] for s in statuses if s['status'] == 'ready']
    unavailable = [s['filename'] for s in statuses if s['status'] != 'ready']
    prefix = ('【本轮材料范围】仅当前勾选文件的本轮参考可作为材料依据；'
              '不引用历史对话里已取消勾选的文件、旧版批改或未在本轮提供的诊断。\n'
              '已提供当前批改参考：' + ('、'.join(ready) or '无') + '。\n')
    if unavailable:
        prefix += '以下文件本轮仅有原文参考，不能声称读取了其批改：' + '、'.join(unavailable) + '。\n'
    prefix += '回答注明文件名与PDF页码，区分原文事实、模型理解和批改建议。\n\n'
    params['text'] = prefix + (params.get('text') or '')
    for model, text in (params.get('question_with_history') or {}).items():
        params['question_with_history'][model] = prefix + text


def public_status(items):
    return [{k: v for k, v in item.items() if not k.startswith('_')} for item in items]


def _text(value):
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        return '；'.join(_text(v) for v in value if isinstance(v, str))
    return ''


def build_chunks(item):
    """白名单抽取，技术审计和思考内容永不送进问答。"""
    from langchain_core.documents import Document
    report = item['_report']
    metadata = {'type': 'grading', 'filename': item['filename'], 'analysis_id': item['analysis_id'],
                'run_id': item['run_id'], 'grading_version': item['version'],
                'source_document_sha256': item['_source_hash'], 'workspace': item['_workspace']}
    chunks = []

    def add(kind, page, qid, body, assessment=''):
        if not body.strip():
            return
        location = f'PDF第{page}页' if page else '整份材料概述（非单页证据）'
        header = f"【批改参考｜{item['filename']}｜{location}】\n"
        if assessment:
            header += '批改状态：' + assessment + '\n'
        # 长单元按段存储，每片保留来源，不让一个全文JSON成为检索单元。
        for i in range(0, len(body), 900):
            content = header + body[i:i + 900]
            meta = {**metadata, 'source': item['filename'], 'page': page - 1 if page else '整份材料',
                    'kind': kind, 'pdf_page': page, 'qid_global': qid,
                    'content_fingerprint': _digest(content)}
            chunks.append(Document(page_content=content, metadata=meta))

    overview = report.get('open_material_overview') or {}
    diagnosis = report.get('diagnosis') or {}
    summary = '\n'.join(filter(None, [_text(overview.get('subject_and_layout')),
                        _text(overview.get('content_review')), _text(diagnosis.get('summary'))]))
    add('summary', 0, '', '批改概述：' + (summary[:500] or '已完成批改，详见各页证据。'))
    for zone, label in (('blind_spot', '盲区'), ('friction_zone', '内耗区'), ('zpd', '最近发展区')):
        for entry in (report.get('zone_classification') or {}).get(zone) or []:
            refs = entry.get('evidence_question_ids') or []
            valid = {f"p{p['page']}:{q.get('id')}" for p in item['_pages'] for q in p.get('questions') or []}
            refs = [ref for ref in refs if ref in valid]
            if not refs:
                continue
            page = int(refs[0].split(':')[0][1:])
            add('zone', page, refs[0], label + '批改建议：' + _text(entry.get('comment')) + '\n' +
                _text(entry.get('suggested_next_step')) + '\n依据：' + '、'.join(refs))
    feedback = {str(f.get('qid_global') or f"p{f.get('page')}:{f.get('id')}"): f
                for f in report.get('per_question_feedback') or [] if isinstance(f, dict)}
    for page in item['_pages']:
        num = int(page['page'])
        ctx = display_context(num, report, item.get('_context'), item['_manifest'])
        add('page', num, '', '材料背景：' + ' · '.join(ctx[k] for k in (
            'education_level_label', 'grade_label', 'subject_label', 'unit_label')) + '\n理解摘要：' + ctx['understanding_summary'])
        for q in page.get('questions') or []:
            qid = f"p{num}:{q.get('id')}"
            labels = [('stem_excerpt', '原文题干／材料'), ('student_answer', '识别到的作答／手写'),
                      ('understanding', '模型理解'), ('printed_text_marked', '印刷文字颜色标记'),
                      ('handwritten_text_marked', '手写颜色标记')]
            body = '\n'.join(label + '：' + _text(q.get(key)) for key, label in labels if _text(q.get(key)))
            status = {'correct': '正确', 'wrong': '错误', 'partial': '部分正确', 'unanswered': '未作答',
                      'uncertain': '待确认'}.get(q.get('verdict'), '未评定')
            if q.get('assessment_status') in ('unconfirmed', 'not_assessed'):
                status = '待确认' if q['assessment_status'] == 'unconfirmed' else '非作答／未评定'
            for link in q.get('annotation_links') or []:
                if isinstance(link, dict):
                    body += '\n标注关系：' + '；'.join(_text(link.get(k)) for k in (
                        'marked_text', 'annotation_text', 'relation') if _text(link.get(k)))
            comment = _text(feedback.get(qid, {}).get('comment'))
            if comment:
                body += '\n批改建议：' + comment
            add('unit', num, qid, body, status)
    return chunks


def _vector_store(workspace):
    from langchain_community.vectorstores import Chroma
    from llm_langchain.parse_input import embeddings, get_user_db_path
    path, _, _ = get_user_db_path(workspace)
    # 使用有界、稳定的ASCII集合名，避免中文用户名触发Chroma集合名限制。
    return Chroma(collection_name='grading-' + _digest(workspace)[:32],
                  embedding_function=embeddings, persist_directory=path)


def ensure_index(item, store):
    from app_chat.ci.file_io import FileLock, atomic_json
    root = Path(item['_root'])
    state_path = root / 'grading_rag_state.json'
    if (root / 'grading_rag.lock').is_symlink():
        raise ValueError('批改索引锁路径无效')
    with FileLock(str(root / 'grading_rag.lock'), timeout=2):
        state = _index_state(root)
        chunks = build_chunks(item)
        ids = ['hg-' + _digest([item['version'], i, c.page_content]) for i, c in enumerate(chunks)]
        if state.get('version') == item['version'] and state.get('status') == 'ready':
            existing = store.get(ids=ids, include=['metadatas'])
            if set(existing.get('ids') or []) == set(ids):
                return chunks
        atomic_json(state_path, {'schema_version': INDEX_SCHEMA, 'version': item['version'], 'status': 'indexing'})
        try:
            for offset in range(0, len(chunks), 32):
                store.add_documents(chunks[offset:offset + 32], ids=ids[offset:offset + 32])
            atomic_json(state_path, {'schema_version': INDEX_SCHEMA, 'version': item['version'],
                                    'status': 'ready', 'chunk_count': len(chunks)})
            return chunks
        except Exception as exc:
            atomic_json(state_path, {'schema_version': INDEX_SCHEMA, 'version': item['version'],
                                    'status': 'failed', 'message': '批改参考索引失败，可在下次问答时重试。',
                                    'error_type': type(exc).__name__})
            raise


def _retrieve(items, question, enhanced=False):
    documents, statuses = [], []
    stores = {}
    for item in items:
        status = public_status([item])[0]
        if item['status'] != 'available':
            statuses.append(status)
            continue
        try:
            workspace = item['_workspace']
            if workspace not in stores:
                stores[workspace] = _vector_store(workspace)
            store = stores[workspace]
            chunks = ensure_index(item, store)
            retrieved = store.max_marginal_relevance_search(
                question or '材料主要内容与批改建议', k=5 if enhanced else 8,
                fetch_k=10 if enhanced else 16, lambda_mult=0.7,
                filter={'grading_version': item['version']})
            # 即便底层检索异常返回其他集合内容，也不得越过本轮文件/版本边界。
            allowed = {c.metadata['content_fingerprint'] for c in chunks}
            retrieved = [d for d in retrieved if d.metadata.get('grading_version') == item['version']
                         and d.metadata.get('workspace') == workspace
                         and d.metadata.get('content_fingerprint') in allowed]
            documents.append([next(c for c in chunks if c.metadata['kind'] == 'summary')] +
                             [d for d in retrieved if d.metadata.get('kind') != 'summary'])
            status.update(status='ready', index_status='ready', message='已使用当前已完成批改。')
        except Exception as exc:
            logger.warning('批改检索失败：%s', type(exc).__name__)
            status.update(status='failed', index_status='failed', message='批改参考检索失败，本轮仅使用原文，可重试。')
        statuses.append(status)
    return documents, statuses


def _start_job(key, fn):
    with _jobs_lock:
        if key in _jobs:
            return _jobs[key]
        if not _slots.acquire(blocking=False):
            return None
        # 仅保留有限的已完成任务，运行中的同一请求复用原线程。
        for old in list(_jobs):
            if len(_jobs) < 16:
                break
            if _jobs[old]['event'].is_set():
                del _jobs[old]
        job = {'event': threading.Event()}
        _jobs[key] = job

    def work():
        try:
            job['result'] = fn()
        except Exception as exc:
            job['error'] = type(exc).__name__
        finally:
            job['event'].set()
            _slots.release()
    threading.Thread(target=work, name='grading-reference', daemon=True).start()
    return job


def retrieve_selection(selection, question, enhanced=False, wait_seconds=WAIT_SECONDS):
    items = selection['items']
    if not any(x['status'] == 'available' for x in items):
        return [], public_status(items)
    key = _digest([selection['cache_key'], question, enhanced])
    job = _start_job(key, lambda: _retrieve(items, question, enhanced))
    if job and job['event'].wait(wait_seconds) and 'result' in job:
        with _jobs_lock:
            _jobs.pop(key, None)
        return copy.deepcopy(job['result'])
    if job and job['event'].is_set():
        with _jobs_lock:
            _jobs.pop(key, None)
    statuses = public_status(items)
    for status in statuses:
        if status['status'] == 'available':
            status.update(status='failed' if job and job.get('error') else 'pending',
                          message='批改参考暂未准备完成，本轮仅使用原文，请稍后再次提问。')
    return [], statuses


def merge_context(original, documents, statuses, budget):
    """先均衡概述，再轮流取细节；保留原文，批改只使用剩余预算。"""
    from langchain_core.documents import Document
    used = sum(len(d.page_content) for group in original for d in group)
    remaining = min(MAX_CHARS, max(0, int(budget) - used))
    output = []
    included = set()
    seen = set()
    for index in range(max((len(group) for group in documents), default=0)):
        for group in documents:
            if index >= len(group):
                continue
            doc = group[index]
            identity = (doc.metadata['grading_version'], doc.metadata['content_fingerprint'])
            if identity in seen:
                continue
            prefix = GUIDANCE if not output else ''
            text = prefix + doc.page_content
            if len(text) > remaining:
                continue
            output.append(Document(page_content=text, metadata=dict(doc.metadata)))
            included.add(doc.metadata['filename'])
            seen.add(identity)
            remaining -= len(text)
    for status in statuses:
        if status['status'] == 'ready' and status['filename'] not in included:
            status.update(status='limited', message='本轮原文已占满参考篇幅，未加入此材料批改；可减少勾选或使用相关检索。')
    return original + ([output] if output else [])


def append_grading_context(original, workspace, filenames, question, *, selection=None, enhanced=False):
    from llm_langchain import global_var
    selection = selection if selection is not None else inspect_selection(workspace, filenames)
    documents, statuses = retrieve_selection(selection, question, enhanced)
    # 建索引或查询期间可能发生重跑：发送前再次核实，绝不使用旧版结果。
    current = inspect_selection(workspace, filenames)
    valid = {i.get('version') for i in current['items'] if i['status'] == 'available'}
    documents = [group for group in documents if group and group[0].metadata.get('grading_version') in valid]
    for status in statuses:
        if status.get('version') and status['version'] not in valid:
            status.update(status='unavailable', message='批改版本已变化，本轮暂仅使用原文。')
    budget = int(global_var.max_token_num[0] / global_var.token_per_char - global_var.left_char_for_prompt_answer)
    merged = merge_context(original, documents, statuses, budget)
    selection['result_status'] = statuses
    return merged


def schedule_index(workspace, filename):
    """完成后预建索引；所有异常都局限于派生索引，不回写批改失败。"""
    try:
        selection = inspect_selection(workspace, [filename])
        for item in selection['items']:
            if item['status'] == 'available':
                _start_job('index-' + item['version'], lambda item=item: ensure_index(item, _vector_store(workspace)))
    except Exception as exc:
        logger.warning('批改参考预建索引未启动：%s', type(exc).__name__)
