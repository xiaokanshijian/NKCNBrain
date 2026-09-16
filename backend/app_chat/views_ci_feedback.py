# -*- coding: utf-8 -*-
"""
图无损理解反馈迭代文本：根据卡片附图的 CI 分析结果，用 Claude 生成增/改建议并写回卡片内容。
支持 <第n次修改内容> 标签包裹、lastContent 留存与回退。
"""
import re
import json

from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse

from app_chat.models import Card
from app_chat.ci_result_adapter import fetch_ci_digest, fetch_ci_digest_by_files, fetch_ci_digest_with_layers
from app_chat.continuous_image_service import CIIndexManager
from app_chat import claude_api
from app_chat.views_card_image import _card_has_image


CI_FEEDBACK_RESULT_LAYERS = 'tm'


def _max_edit_tag_n(content):
    """从正文中解析已有 <第n次修改内容> 的最大 n。"""
    if not content:
        return 0
    matches = re.findall(r'<第\s*(\d+)\s*次修改内容>', content)
    if not matches:
        return 0
    return max(int(m) for m in matches)


def _strip_thinking_blocks(text):
    """去掉 ```thinking / ```checking 等块，只保留正文。"""
    if not text:
        return text
    for pattern in (r'```thinking[\s\S]*?```', r'```checking[\s\S]*?```', r'```[\s\S]*?```'):
        text = re.sub(pattern, '', text)
    return text.strip()


def _extract_json_from_response(text):
    """从模型输出中提取 JSON：优先 ```json ... ```，否则取首尾 {} 之间的内容。"""
    if not text:
        return None
    text = text.strip()
    m = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
    if m:
        return m.group(1).strip()
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _normalize_whitespace_for_match(s):
    """将空白规范为单一空格，便于匹配原文。"""
    if not s:
        return s
    return ' '.join(s.split())


def _find_anchor(content, anchor, try_normalize=True):
    """在 content 中查找 anchor，返回 (start, end)。优先精确匹配；失败则用规范化空白后再匹配并映射回原文区间。"""
    if not anchor or not content:
        return None
    pos = content.find(anchor)
    if pos != -1:
        return (pos, pos + len(anchor))
    if not try_normalize:
        return None
    norm_content = _normalize_whitespace_for_match(content)
    norm_anchor = _normalize_whitespace_for_match(anchor)
    pos = norm_content.find(norm_anchor)
    if pos == -1:
        return None
    # 原文到规范化串的索引映射：norm_content 的每个字符对应原文的 (start,end)
    tokens = content.split()
    norm_to_orig = []
    pos = 0
    for ti, tok in enumerate(tokens):
        for _ in tok:
            norm_to_orig.append((pos, pos + 1))
            pos += 1
        if ti < len(tokens) - 1:
            norm_to_orig.append((pos, pos + 1))  # 一个空格
            pos += 1
            while pos < len(content) and content[pos].isspace():
                pos += 1
    if pos + len(norm_anchor) > len(norm_to_orig):
        return None
    start_in_orig = norm_to_orig[pos][0]
    end_in_orig = norm_to_orig[min(pos + len(norm_anchor), len(norm_to_orig)) - 1][1]
    return (start_in_orig, end_in_orig)


def _apply_edits_to_content(original_content, edits, n_tag):
    """先在原文上解析每条编辑的起止位置，再按位置从后往前应用，避免第二条及后续在已改动正文里找不到片段。"""
    if not edits:
        return (original_content, None)
    tag_open = '<第%d次修改内容>' % n_tag
    tag_close = '</第%d次修改内容>' % n_tag
    # 第一遍：全部在原文中定位，得到 (start, end, typ, new_text)
    resolved = []
    for i, edit in enumerate(edits):
        if not isinstance(edit, dict):
            return (None, '第 %d 条编辑格式错误' % (i + 1))
        typ = edit.get('type')
        old = edit.get('old')
        anchor = edit.get('anchor')
        new = edit.get('new') or ''
        if typ == 'replace':
            if not old:
                return (None, '第 %d 条 replace 缺少 old' % (i + 1))
            span = _find_anchor(original_content, old)
            if span is None:
                return (None, '第 %d 条 replace 在正文中找不到对应 old 片段（请确保 old 从原文逐字复制）' % (i + 1))
            start, end = span
            resolved.append((start, end, 'replace', new))
        elif typ == 'insert_after':
            if not anchor:
                return (None, '第 %d 条 insert_after 缺少 anchor' % (i + 1))
            span = _find_anchor(original_content, anchor)
            if span is None:
                return (None, '第 %d 条 insert_after 在正文中找不到 anchor（请确保 anchor 从原文逐字复制）' % (i + 1))
            _, end = span
            resolved.append((end, end, 'insert', new))
        else:
            return (None, '第 %d 条编辑 type 须为 replace 或 insert_after' % (i + 1))
    # 按 start 从大到小应用，这样前面的位置不会因后面的修改而偏移
    resolved.sort(key=lambda x: x[0], reverse=True)
    content = original_content
    for start, end, typ, new in resolved:
        if typ == 'replace':
            content = content[:start] + tag_open + new + tag_close + content[end:]
        else:
            content = content[:start] + '\n' + tag_open + new + tag_close + content[start:]
    return (content, None)


@csrf_exempt
def card_list_ci_analyses_for_feedback(request):
    """列出当前用户所有已完成的 CI 分析，供「图无损理解反馈迭代文本」选择。
    POST { username } → { error_num, analyses: [{ analysis_id, mode, files, created_at }, ...] }
    """
    if request.method != 'POST':
        print("[CI反馈] error_num: 1, msg: 仅支持 POST")
        return JsonResponse({'error_num': 1, 'msg': '仅支持 POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        if not username:
            print("[CI反馈] error_num: 1, msg: 缺少 username")
            return JsonResponse({'error_num': 1, 'msg': '缺少 username'})
        all_recs = CIIndexManager.load(username)
        completed = [
            {
                'analysis_id': r.get('analysis_id', ''),
                'mode': r.get('mode', ''),
                'files': r.get('files', []),
                'created_at': r.get('created_at', ''),
            }
            for r in all_recs
            if r.get('status') == 'completed'
        ]
        completed.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        return JsonResponse({'error_num': 0, 'analyses': completed})
    except Exception as e:
        print("[CI反馈] error_num: 1, msg:", str(e))
        return JsonResponse({'error_num': 1, 'msg': str(e)})


@csrf_exempt
def card_ci_feedback_iterate_content(request):
    """根据指定 CI 分析结果，用 Claude 对卡片正文做一轮「图无损理解反馈」迭代，写回 content 并留存 lastContent。
    POST { username, cid, analysis_id? } 或 { username, cid, files? }
    若两者都未传则返回 error，提示传入 analysis_id 或 files。
    """
    if request.method != 'POST':
        print("[CI反馈] error_num: 1, msg: 仅支持 POST")
        return JsonResponse({'error_num': 1, 'msg': '仅支持 POST'})
    try:
        data = json.loads(request.body)
        username = (data.get('username') or '').strip()
        cid = data.get('cid')
        analysis_id = data.get('analysis_id')
        files = data.get('files')

        if not username or cid is None:
            print("[CI反馈] error_num: 1, msg: 缺少 username 或 cid")
            return JsonResponse({'error_num': 1, 'msg': '缺少 username 或 cid'})
        cid = int(cid)

        card = Card.objects.get(cid=cid, username=username)
        if not _card_has_image(username, cid):
            print("[CI反馈] error_num: 1, msg: 该卡片无附图，无法使用图无损理解反馈")
            return JsonResponse({'error_num': 1, 'msg': '该卡片无附图，无法使用图无损理解反馈'})

        if analysis_id:
            # digest = fetch_ci_digest(username, analysis_id)
            digest = fetch_ci_digest_with_layers(
                username,
                analysis_id,
                result_layers=CI_FEEDBACK_RESULT_LAYERS,
            )
        elif files and isinstance(files, list) and len(files) > 0:
            # digest = fetch_ci_digest_by_files(username, [f for f in files if f])
            digest = fetch_ci_digest_by_files(
                username,
                [f for f in files if f],
                result_layers=CI_FEEDBACK_RESULT_LAYERS,
            )
        else:
            print("[CI反馈] error_num: 1, msg: 请传入 analysis_id 或 files 以指定使用的图片理解结果")
            return JsonResponse({'error_num': 1, 'msg': '请传入 analysis_id 或 files 以指定使用的图片理解结果'})

        if not digest.get('ok'):
            err = digest.get('error', '获取图片理解结果失败')
            print("[CI反馈] error_num: 1, msg:", err)
            return JsonResponse({'error_num': 1, 'msg': err})

        current_content = (card.content or '').strip()
        composite = (digest.get('composite_text') or '').strip()
        core_theme = (digest.get('core_theme') or '').strip()
        overall = (digest.get('overall_summary') or '').strip()
        n_next = _max_edit_tag_n(current_content) + 1

        system = """你是专业的内容修订助手。根据「图片无损理解」分析结果，对卡片正文做**精准、可程序解析**的增补与修改。

输出格式（必须严格遵守）：
只输出一个 JSON 对象，不要任何解释、markdown 包裹或多余文字。格式如下：
{"edits": [
  {"type": "replace", "old": "从原文中复制的连续片段（至少20字，且全文唯一）", "new": "替换后的内容"},
  {"type": "insert_after", "anchor": "从原文中复制的连续片段（至少15字，用于定位插入位置）", "new": "在 anchor 后插入的内容"}
]}

规则：
1. "old" 和 "anchor" 必须从用户提供的【当前卡片正文】中**逐字复制**，保证在正文中唯一出现；多条编辑之间 "old" 不得重叠。
2. 修改要有**击穿性**：融入上下文逻辑与表述，不是简单的改写、补全句子，而是真正深入理解的提升性修改（replace），以及避免只在某处生硬加一段（insert_after 仅当确实需要新增独立句段时使用）。不要大段堆砌，要精准落在需要改的地方。
3. **严禁 AI 腔和废话**：禁止使用「值得注意的是」「综上所述」「从某种意义上说」「可以这样理解」「总体来看」等套话；禁止空洞总结、重复原文意思的“不错但没有提升价值的废话”。修改要简单而深刻、有信息量，语气与原文一致（学术则学术，口语则口语）。
4. 若无需修改，输出 {"edits": []}。"""

        user = """【当前卡片正文】
%s

【附图的无损理解分析结果（供你参考以增补/修正正文）】
%s
%s
%s

请根据上述图片理解结果，输出**仅一个 JSON 对象**（edits 数组），指定在正文的哪些位置做 replace 或 insert_after，做到精准无歧义。不要输出其它任何内容。""" % (
            current_content[:12000],
            f"【核心主题】{core_theme}\n\n" if core_theme else "",
            f"【整体摘要】\n{overall}\n\n" if overall else "",
            composite[:8000],
        )

        # 3 次机会：先 claude-sonnet-4.5，失败则 claude-sonnet-4，再失败则 3.7
        CI_FEEDBACK_MODELS = [
            "claude-sonnet-4-5-20250929",   # claude-sonnet-4.5
            "claude-sonnet-4-20250514",     # claude-sonnet-4
            "claude-3-7-sonnet-20250219",   # 3.7
        ]
        raw = None
        last_error = None
        for model in CI_FEEDBACK_MODELS:
            try:
                raw = claude_api.make_claude_text_requests(user, system, model=model)
                if raw and len((raw or "").strip()) >= 2:
                    break
            except Exception as e:
                last_error = e
                continue
        raw = _strip_thinking_blocks(raw or "")
        json_str = _extract_json_from_response(raw)
        if not json_str:
            err_msg = str(last_error) if last_error else 'Claude 未返回有效内容'
            print("[CI反馈] error_num: 1, msg: Claude 三次尝试均未成功，最后错误:", err_msg)
            return JsonResponse({'error_num': 1, 'msg': f'Claude 三次尝试均未成功，请重试。最后错误：{err_msg}'})
        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            print("[CI反馈] error_num: 1, msg: Claude 返回的 JSON 解析失败:", str(e))
            return JsonResponse({'error_num': 1, 'msg': 'Claude 返回的 JSON 解析失败：%s' % str(e)})
        edits = parsed.get('edits')
        if edits is None:
            print("[CI反馈] error_num: 1, msg: JSON 中缺少 edits 字段")
            return JsonResponse({'error_num': 1, 'msg': 'JSON 中缺少 edits 字段'})
        if not isinstance(edits, list):
            print("[CI反馈] error_num: 1, msg: edits 须为数组")
            return JsonResponse({'error_num': 1, 'msg': 'edits 须为数组'})
        new_content, apply_err = _apply_edits_to_content(current_content, edits, n_next)
        if apply_err:
            print("[CI反馈] error_num: 1, msg: 应用编辑失败:", apply_err)
            return JsonResponse({'error_num': 1, 'msg': '应用编辑失败：%s' % apply_err})
        if not new_content or len(new_content) < 10:
            print("[CI反馈] error_num: 1, msg: 应用编辑后内容无效")
            return JsonResponse({'error_num': 1, 'msg': '应用编辑后内容无效'})

        card.lastContent = card.content or ""
        card.content = new_content
        card.save(update_fields=['content', 'lastContent'])

        return JsonResponse({
            'error_num': 0,
            'msg': 'success',
            'content': card.content,
            'lastContent': card.lastContent,
        })
    except Card.DoesNotExist:
        print("[CI反馈] error_num: 1, msg: 卡片不存在")
        return JsonResponse({'error_num': 1, 'msg': '卡片不存在'})
    except Exception as e:
        print("[CI反馈] error_num: 1, msg:", str(e))
        return JsonResponse({'error_num': 1, 'msg': str(e)})
