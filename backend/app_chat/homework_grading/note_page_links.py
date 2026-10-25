"""笔记混排页的保守候选关联；印刷页码不是 PDF 序号，也不证明题目已补全。"""
from .note_evidence import normalize_page_origin
from .utils import safe_json_dump


def candidate_note_page_pairs(pages):
    pairs = []
    for page, data in pages.items():
        origin = normalize_page_origin(data.get('page_origin'))
        number = origin['printed_page_number']
        if number is None or origin['source_kind'] not in ('textbook', 'workbook'):
            continue
        candidates = []
        for other, target in pages.items():
            dest = normalize_page_origin(target.get('page_origin'))
            if dest['source_kind'] != origin['source_kind'] or dest['printed_page_number'] != number + 1:
                continue
            if origin['source_title'] and dest['source_title'] and origin['source_title'] != dest['source_title']:
                continue
            # 双方均需有延续证据，不能将两个完整页面强行拼成一题。
            if not (data.get('boundary', {}).get('continues_to_next')
                    and target.get('boundary', {}).get('continues_from_prev')):
                continue
            candidates.append(other)
        if len(candidates) == 1:
            other = candidates[0]
            # 同号来源不唯一时不自动选择一本书。
            duplicates = [p for p, d in pages.items()
                          if normalize_page_origin(d.get('page_origin')) == origin]
            if len(duplicates) == 1:
                pairs.append([page, other])
    return pairs


def backfill_note_detect_dir(pass1_dir):
    from .parent_stem_backfill import _iter_detect_json_files
    items = _iter_detect_json_files(pass1_dir)
    pages = {page: data for page, _, data in items}
    pairs = candidate_note_page_pairs(pages)
    for page, path, data in items:
        # 保留原始题号和单页边界；候选上下文不能伪装成完成的跨页作答。
        data['note_page_link_candidates'] = [pair for pair in pairs if page in pair]
        for q in data.get('questions') or []:
            q.pop('cross_page_context_ready', None)
        safe_json_dump(path, data)
    return {'candidate_pairs': pairs, 'pages_written': len(items)}
