"""确定性范围和声明冲突组合；不让模型决定规则优先级。"""
import copy

from .feedback_context import freeze_feedback_context
from .feedback_skills import load_registry, validate_manifest


def scope_reason(manifest, metadata, unit_type='question'):
    if manifest['kind'] == 'general':
        return None
    for key, value in [('subject_scope', metadata['subject_code']),
                       ('education_scope', metadata['education_level']),
                       ('material_scope', metadata['material_type']), ('unit_scope', unit_type)]:
        if '*' not in manifest[key] and value not in manifest[key]:
            return '范围不匹配：' + key
    if manifest['grades'] and (metadata['grade_status'] != 'resolved' or metadata.get('grade_in_level') not in manifest['grades']):
        return '年级未知、冲突或不在专项范围'
    return None


def _narrower(a, b):
    strict = False
    for key in ('subject_scope','education_scope','material_scope','unit_scope','grades'):
        av, bv = set(a[key]), set(b[key])
        aw, bw = ('*' in av or not av), ('*' in bv or not bv)
        if aw and not bw:
            return False
        if not bw and not av <= bv:
            return False
        strict |= (not aw and bw) or (not aw and not bw and av < bv)
    return strict


def _conflicts(a, b):
    for ra in a['rules']:
        for rb in b['rules']:
            if ra['id'] in rb.get('conflicts',[]) or rb['id'] in ra.get('conflicts',[]):
                return True
            # 显式细化也必须经过完整范围与优先级裁决，不能绕过范围门控。
            if ra['id'] in rb.get('refines', []) or rb['id'] in ra.get('refines', []):
                return True
            if ra['evaluation_item'] == rb['evaluation_item'] and ra['id'] != rb['id']:
                return True
    return False


def compose_skills(metadata, skills=None, *, unit_type='question', exclusions=None):
    if skills is None:
        skills, registry_exclusions = load_registry()
    else:
        registry_exclusions = []
    excluded = copy.deepcopy((exclusions or []) + registry_exclusions)
    candidates=[]
    for skill in skills:
        manifest=skill['content']['manifest']
        validate_manifest(manifest)
        reason=scope_reason(manifest,metadata,unit_type)
        if reason:
            excluded.append({'id':skill['id'],'reason':reason})
        else:
            candidates.append(copy.deepcopy(skill))
    general=[s for s in candidates if s['content']['manifest']['kind']=='general']
    if len(general)!=1:
        raise ValueError('必须有唯一通用规则')
    special=[s for s in candidates if s not in general]
    rejected={}
    for i,a in enumerate(special):
        ma=a['content']['manifest']
        for b in special[i+1:]:
            mb=b['content']['manifest']
            if not _conflicts(ma,mb):
                continue
            if _narrower(ma,mb):
                rejected[b['id']]='被更精确范围的专项替代'
            elif _narrower(mb,ma):
                rejected[a['id']]='被更精确范围的专项替代'
            elif all(set(ma[k])==set(mb[k]) for k in ('subject_scope','education_scope','material_scope','unit_scope','grades')) and ma['priority']!=mb['priority']:
                rejected[(a if ma['priority']<mb['priority'] else b)['id']]='被更高优先级专项替代'
            else:
                rejected[a['id']]=rejected[b['id']]='同级或不可比较范围专项冲突，保留通用能力'
    selected=general+sorted([s for s in special if s['id'] not in rejected],key=lambda s:(s['content']['manifest']['priority'],s['id'],s['version']))
    excluded += [{'id':k,'reason':v} for k,v in sorted(rejected.items())]
    # 规则身份相同必须正文相同；不允许通过重复ID偷偷覆盖。
    seen={}
    for skill in selected:
        for rule in skill['content']['manifest']['rules']:
            value=skill['content']['resources']['texts'][rule['text_key']]
            if rule['id'] in seen and seen[rule['id']] != (rule,value):
                raise ValueError('重复规则标识的内容或条件不一致')
            seen[rule['id']]=(rule,value)
    audit={'included':[{'id':s['id'],'version':s['version'],'reason':'通用必选' if s in general else '完整范围匹配'} for s in selected], 'excluded':excluded,
           'execution_order':[s['id'] for s in selected]}
    return selected,audit


def bind_skills(metadata, *, skills=None, curriculum_binding=None):
    selected,audit=compose_skills(metadata,skills)
    context=freeze_feedback_context(metadata,skill_bindings=[{k:s[k] for k in ('id','version','content_hash')} for s in selected],curriculum_binding=curriculum_binding)
    return context,selected,audit
