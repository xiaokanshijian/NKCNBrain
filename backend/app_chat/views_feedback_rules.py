"""管理页批改规则 CRUD；只操作固定受管规则文件。"""
import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from app_chat.homework_grading.managed_feedback_rules import (
    OWNERSHIP_ITEMS, compose_skill_md_preview, delete_rule, list_rule_history,
    list_rules, restore_builtin_bodies, restore_rule_body, rollback_rule,
    rule_options, save_rule,
)
from app_chat.homework_grading.yangqian_debug import debug_log


def _body(request):
    try:
        value = json.loads(request.body or b'{}')
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError('请求JSON无效') from exc
    if not isinstance(value, dict):
        raise ValueError('请求数据必须为对象')
    return value


@csrf_exempt
def feedback_rules(request):
    try:
        if request.method == 'GET':
            history_of = (request.GET.get('history_of') or '').strip()
            if history_of:
                return JsonResponse({'error_num': 0, 'msg': 'success', 'history': list_rule_history(history_of)})
            rules = list_rules()
            return JsonResponse({'error_num': 0, 'msg': 'success', 'rules': rules,
                                 'skill_md_preview': compose_skill_md_preview(rules),
                                 'ownership_items': OWNERSHIP_ITEMS, 'options': rule_options()})
        if request.method == 'POST':
            data = _body(request)
            if data.get('rollback'):
                if set(data) - {'id', 'history_id', 'rollback'}:
                    raise ValueError('回滚请求只接受规则ID和历史版本ID')
                rule = rollback_rule(data.get('id'), data.get('history_id'))
                debug_log(f"[feedback_rules] 回滚成功 id={data.get('id')} history_id={data.get('history_id')}")
                return JsonResponse({'error_num': 0, 'msg': 'success', 'rule': rule})
            if data.get('restore_all'):
                if set(data) - {'restore_all', 'restore_factory'}:
                    raise ValueError('整包恢复出厂只接受 restore_all')
                result = restore_builtin_bodies()
                return JsonResponse({'error_num': 0, 'msg': 'success', **result})
            if data.get('restore_factory'):
                if set(data) - {'id', 'restore_factory'}:
                    raise ValueError('恢复出厂请求只接受规则ID')
                rule = restore_rule_body(data['id'])
                return JsonResponse({'error_num': 0, 'msg': 'success', 'rule': rule})
            rule = save_rule(data)
            debug_log(f"[feedback_rules] 保存成功 id={rule.get('id')} name={rule.get('name')}")
            return JsonResponse({'error_num': 0, 'msg': 'success', 'rule': rule})
        if request.method == 'DELETE':
            data = _body(request)
            if set(data) != {'id'}:
                raise ValueError('删除请求只接受规则ID')
            deleted = delete_rule(data['id'])
            return JsonResponse({'error_num': 0, 'msg': 'success', 'deleted': deleted})
        return JsonResponse({'error_num': 1, 'msg': '仅支持GET、POST、DELETE'}, status=405)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return JsonResponse({'error_num': 1, 'msg': str(exc)})
