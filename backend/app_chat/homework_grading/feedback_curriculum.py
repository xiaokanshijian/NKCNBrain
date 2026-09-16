"""P02既有S1-S3内容适配，不导入S4或用户课程，不用旧年级兜底。"""
import hashlib
import json
import re
from pathlib import Path

from .feedback_fingerprint import content_sha256


def _selected_stage(context, resource):
    tree=resource.get('content')
    if not isinstance(tree,dict) or tree.get('subject')!=context['subject_code']:
        raise ValueError('课程内容与材料学科不一致')
    key=resource.get('stage_key')
    if key not in ('S1','S2','S3') or context['education_level']!='primary' or context['grade_status']!='resolved':
        raise ValueError('当前材料不在P02既有课程覆盖范围')
    stages=[s for s in tree.get('stages',[]) if s.get('stage')==int(key[1:])]
    if len(stages)!=1:raise ValueError('课程阶段缺失或不唯一')
    stage=stages[0];band=re.fullmatch(r'(\d+)\s*-\s*(\d+)',str(stage.get('grade_band','')))
    if not band or not int(band[1])<=context['grade_in_level']<=int(band[2]):
        raise ValueError('课程声明年级不覆盖当前材料')
    return stage


def freeze_builtin_curriculum(metadata):
    subject=metadata['subject_code']
    if subject not in ('math','chinese','english') or metadata['education_level']!='primary' or metadata['grade_status']!='resolved':
        return None
    path=Path(__file__).parent/'data/curriculum'/f'{subject}_curriculum.json'
    raw=path.read_bytes();tree=json.loads(raw)
    candidates=[]
    for stage in tree.get('stages',[]):
        if stage.get('stage') not in (1,2,3):continue
        resource={'resource_id':f'builtin-{subject}-s1-s3','version':'sha256:'+hashlib.sha256(raw).hexdigest(),
                  'stage_key':f"S{stage['stage']}",'content':tree,'content_hash':content_sha256(tree),
                  'scope':{'education_level':'primary','grade_band':stage['grade_band']},'coverage_status':'existing_s1_s3'}
        try:_selected_stage(metadata,resource)
        except ValueError:continue
        candidates.append(resource)
    if len(candidates)>1:raise ValueError('内置课程范围不唯一，必须明确选择')
    return candidates[0] if candidates else None


def curriculum_entries(runtime):
    resource=runtime.dependencies['curriculum']
    if resource is None:return []
    stage=_selected_stage(runtime.context,resource)
    result=[];ids=set()
    for domain in stage.get('domains',[]):
        for kp in domain.get('knowledge_points',[]):
            if not kp.get('id') or not kp.get('label') or kp['id'] in ids:raise ValueError('课程知识点缺失身份或重复')
            ids.add(kp['id'])
            result.append(dict(kp,domain=domain['name'],stage=stage['stage']))
    return result
