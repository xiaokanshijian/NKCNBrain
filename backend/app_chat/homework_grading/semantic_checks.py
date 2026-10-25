"""只检查评价句；引述、否定、假设与确定断言分开，不遍历内部审计。"""
import re

BOUNDARY = re.compile(r'[，,。；;！？!?\n]|但是|然而|不过|反而|却|实际上')
DENIAL = re.compile(
    r'(?:(?:尚不能|尚无法|不能|不可|不应|不得|无法|不足以|暂不|尚不|并不|不)'
    r'(?:据此|由此|因此|直接|仅|就|简单|轻易|贸然){0,3}'
    r'(?:推断|断定|认定|判定|判断|说明|证明|视为|当作|归为|确定|确认|认为|推定|归入|看作|当成|认作|判|作|按|得出)'
    r'|(?:不代表|不意味着|并不说明|并非|不是|不属于|并不是)'
    r'|(?:没有|尚无|暂无|缺乏)(?:任何|足够|充分|可靠|直接|明确|可用|相应|的)*'
    r'(?:证据|依据)(?:能够|可以|能|可|足以)?(?:表明|证明|说明|支持|认定))'
    r'(?:学生|该生|你|他|她|孩子|为|是|存在|其|已经|是否|有|“|‘|「|\")*$')
DOUBLE = re.compile(r'(?:并非|不是|并不是|不能|不可|不应|不得|无法)(?:说|认定|认为|断定)?\s*$')
QUOTES = re.compile(r'“[^”]*”|「[^」]*」|‘[^’]*’|"[^"\n]*"')
SOURCE = re.compile(r'(?:原文|题干|原句|转写|旁批|学生写|引用|例如|例子)[^，。；\n]{0,15}$')


def phrase_findings(text, pattern):
    text = str(text or '')
    quoted = [(m.start(), m.end()) for m in QUOTES.finditer(text)
              if SOURCE.search(text[max(0, m.start()-30):m.start()])]
    result = []
    for match in re.finditer(pattern, text):
        if any(start <= match.start() < end for start, end in quoted):
            continue
        prefix = BOUNDARY.split(text[:match.start()])[-1].strip()
        denial = DENIAL.search(prefix)
        if not denial:
            # 同一否定判断下的并列宾语：不能据此判断学生“不会或未掌握”。
            # 仅消去由“或/和/及”连接的能力词，不跨越分句、转折或新的谓语。
            coordinated = re.sub(r'(?:(?:不会|未掌握|掌握|会|答错|漏答|不正确)(?:或|和|及|以及))+\s*$', '', prefix)
            denial = DENIAL.search(coordinated)
            if denial and DOUBLE.search(coordinated[:denial.start()]):
                denial = None
        if denial and not DOUBLE.search(prefix[:denial.start()]):
            continue
        action_denial = re.search(r'(?:不|无需|不必)$', prefix)
        if (action_denial and re.match(r'需要|必须|应当|建议', match.group())
                and not DOUBLE.search(prefix[:action_denial.start()])):
            continue
        kind = 'ambiguous' if re.search(r'是否|能否|如果|假如|假设|可能|似乎|尚待|待核实', prefix) else 'assertion'
        result.append({'kind': kind, 'start': match.start(), 'end': match.end(),
                       'text': match.group(), 'sentence': (prefix + text[match.start():match.end()+25])[:180]})
    return result


TEXT_FIELDS = {'evolution_narrative', 'rationale', 'suggested_next_step', 'summary', 'cognitive_stage',
               'comment', 'content_review', 'subject_and_layout', 'next_steps', 'next_actions',
               'zpd_recommendations', 'cause', 'understanding_summary'}
CONTAINERS = {'zones', 'zone_classification', 'blind_spot', 'friction_zone', 'zpd', 'uncertain',
              'per_question_feedback', 'page_feedback_contexts', 'diagnosis', 'open_material_overview',
              'error_clusters'}


def evaluation_texts(value, path=''):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from evaluation_texts(item, f'{path}/{index}')
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in TEXT_FIELDS or key in CONTAINERS:
                yield from evaluation_texts(item, f'{path}/{key}')
