"""语义关键词规范化 & LLM 四色/DMT 返回值解析（卡片/关键词分析共用）"""
import re
from typing import Any, Dict, List, Optional, Tuple

KEYWORD_MAX_CN_CHARS = 5
KEYWORD_MAX_EN_CHARS = 10

# 建卡 keyWords：数量以合适为准；随正文字数放宽硬上限
CARD_KEYWORDS_SOFT_CAP = 6
CARD_KEYWORDS_HARD_CAP = 10  # ≤3000 字默认硬上限
CARD_KEYWORDS_PREFERRED_MID = 12  # >3000：最好不超
CARD_KEYWORDS_HARD_CAP_MID = 15  # >3000：必要时最大
CARD_KEYWORDS_PREFERRED_LONG = 16  # >4000：最好不超
CARD_KEYWORDS_HARD_CAP_LONG = 20  # >4000：必要时最大
SHORT_CONTENT_CHAR_THRESHOLD = 1500
MID_CONTENT_CHAR_THRESHOLD = 3000
LONG_CONTENT_CHAR_THRESHOLD = 4000
SEMANTIC_KEYWORDS_FINAL_MARKER = '[FINAL]'
# 兼容旧属性分析标记
SEMANTIC_KEYWORDS_FINAL_MARKER_ALT = '【最终结果如下】'
DEFAULT_FINAL_MARKERS = (SEMANTIC_KEYWORDS_FINAL_MARKER, SEMANTIC_KEYWORDS_FINAL_MARKER_ALT)

# 单卡抽词验收：汉字数 ≥ 此值（英文字母/数字不计），或含反引号 ` ，整批视为调用失败并重试
SEMANTIC_KEYWORD_REJECT_MIN_CN_CHARS = 10

# kimi-k2.6 分类任务：关闭 thinking，避免 max_tokens 被推理占满导致 content 为空
KIMI_CLASSIFY_MODEL = 'kimi-k2.6'
KIMI_CLASSIFY_TEMPERATURE = 0.6  # kimi-k2.6 仅允许 0.6
KIMI_CLASSIFY_EXTRA_BODY = {'thinking': {'type': 'disabled'}}
LLM_COLOR_DMT_TWO_LETTER_RULE = '禁止做任何说明，回答必须是两个大写字母，直接给结果'
LLM_SINGLE_LETTER_OUTPUT_RULE = '禁止做任何说明，回答必须是单个大写字母，直接给结果'

_TRIM_SUFFIXES = (
    '设计方案', '设计方法', '设计', '方法论', '方法', '策略', '模式',
    '框架', '体系', '思想', '概念', '应用', '实践', '分析', '研究',
)  # 保留常量供语义梳理等旧逻辑参考；建卡归一化不再做硬截断


def keyword_count_bounds_for_content(content: Optional[str]) -> Tuple[int, int, int]:
    """
    按卡片正文字数给出 (min_count, preferred_max, hard_cap)。
    仅作提示，以「合适、层次够、语义段覆盖全」为准。

    - 字数 < 1500：通常 2～4；硬上限 10
    - 1500～3000：通常 4～6；硬上限 10
    - 字数 > 3000：最好不超 12，必要时最大 15
    - 字数 > 4000：最好不超 16，必要时最大 20
    """
    n = len(content or '')
    if n > LONG_CONTENT_CHAR_THRESHOLD:
        return 6, CARD_KEYWORDS_PREFERRED_LONG, CARD_KEYWORDS_HARD_CAP_LONG
    if n > MID_CONTENT_CHAR_THRESHOLD:
        return 5, CARD_KEYWORDS_PREFERRED_MID, CARD_KEYWORDS_HARD_CAP_MID
    if n < SHORT_CONTENT_CHAR_THRESHOLD:
        return 2, 4, CARD_KEYWORDS_HARD_CAP
    return 4, CARD_KEYWORDS_SOFT_CAP, CARD_KEYWORDS_HARD_CAP


def max_keywords_for_content(content: Optional[str]) -> int:
    """建卡抽取时提示用的「优先上限」（仍允许必要时到 hard_cap）。"""
    return keyword_count_bounds_for_content(content)[1]


def hard_cap_for_content(content: Optional[str]) -> int:
    """建卡抽取解析/截断用的硬上限。"""
    return keyword_count_bounds_for_content(content)[2]


def _reflective_pitfall_examples() -> str:
    """几份评测样例：内容的大致浓缩摘要 + 目标关键词 + 为何优于错误抽法（须对齐此质量）。"""
    return (
        '【强制对齐示范——几份真实评测样例】\n'
        '下面各例给出「卡片内容大致浓缩摘要 + 应抽出的语义关键词」。'
        '抽取任何新卡片时，质量须对齐这些示范的理解深度与取舍逻辑；'
        '严禁再犯各例「错误抽法」里的同类错误。\n'
        '\n'
        '【一眼可读总标准——先读这条再抽】\n'
        '这组语义关键词放在一起，外人应能一眼明白「这张卡在具体讲什么」：'
        '既有立足的具体内容主体（D），又有手段/过程框架（M），也有放眼启示/落点（T）；'
        '三层都要有、缺一不可。比例大致约 5:3:2（指语义比重，不是硬凑 5 个 D / 3 个 M / 2 个 T）。'
        '若一眼只有云里雾里的「体系/机制/转化/分离」印象、猜不出主题与内涵——即失败，必须重抽。'
        '「深刻」= 更准、更贴作者立意的具体说法；绝不是把具体工程/主题压成更抽象的元词。\n'
        '\n'
        '【样例1·摘要】丹李·DRG医学共生本体会议纪要：业务从卖设备转向医保服务、对接医保支付口，'
        '以结果付费合伙人做成价值共赢（非传统甲乙方）；维度从单病升到医疗体系整体运算逻辑。'
        '竞争优势在专病连续结构化数据，区别器械商、SaaS与通用大模型。'
        '强调工程上的医学本体论与三脑协同与人机落地；主张重构底层质量体系而非复制专家，实现知识平权，'
        '从辅助走向引领学科，布局基层云端调用与三甲多病共管生态。\n'
        '【样例1·应输出】DRG，医学本体论，医患共生，价值付费，专病数据，引领学科，多病共管，知识平权\n'
        '【样例1·为何这样抽】'
        '①标题最醒目主体是 DRG，必须居首，绝不可被「医学共生本体」等非原子性的复合词吞掉后消失；'
        '②「医患共生」比「医保共生」可读、贴合共生关系本质；'
        '③文中虽高频「结果付费」，但作者立意是价值共享/分成，应取「价值付费」（或「价值分成」）这一更深说法；'
        '④专病数据、引领学科、知识平权是作者主张与走向，应覆盖；'
        '⑤「语义空间」「工程本体论」过大或与本卡更具体框架重复、非主贡献，应去掉。\n'
        '【样例1·错误抽法（禁止再犯）】'
        '医学共生本体（不原子），医保共生/医保结果付费，语义空间，知识颗粒化，结果付费，工程本体论……'
        '——漏掉 DRG；用看不懂或偏浅的付费说法；塞进过大/重复理论词；缺竞争优势、引领等主张词（需具体，即什么竞争优势、引领什么、什么的发展等）。\n'
        '\n'
        '【样例2·摘要】都江堰灌区从初建几十万亩历经两千余年三次大规模扩充至约1100万亩：'
        '渠首的鱼嘴、飞沙堰、宝瓶口并非为固定规模而设，而是以内外江四六分水等开放式规则自适应扩张；'
        '使下游无论怎样扩张，渠首仍能以恒定物理规律响应；辅以渡槽、隧洞、水库等延伸，'
        '岁修维护即可持续供水，无需重构渠首。真长久在于机制自适应：预留熵减空间吸纳复杂度增量；'
        '底层物理规律与「深淘滩、低作堰」等治理原则稳定时，中间灌区可自由生长，'
        '启示共生组织以核心协同机制支撑长久进化。\n'
        '【样例2·应输出】都江堰，渠首工程，自适应机制，四六分水，熵减空间，共生组织\n'
        '【样例2·为何这样抽】'
        '总实体→工程对象→本卡点名的中层主张「自适应机制」→具体规则「四六分水」→论点「熵减空间」→落点「共生组织」。'
        '注意：此处「自适应机制」是本卡作者明确立住的机制名，不是为了「显得深刻」而硬造的云雾词；'
        '若某卡没有这种点名机制、却有鱼嘴/飞沙堰/宝瓶口等具名实体，应优先抽具名实体（见样例6）。\n'
        '【样例2·错误抽法（禁止再犯）】'
        '都江堰，渠首工程，四六分水，熵减空间，共生组织——缺本卡点名的中层主张「自适应机制」。\n'
        '\n'
        '【样例3·摘要】都江堰治水史中，传统/部落/组织三类知识多次冲突，形成高阻尼：'
        '一是岁修淘滩深度——传统要求淘至卧铁，工匠据部落经验主张淘至卧铁上约一米即可，工程曾停滞数月，'
        '后经实测改为「按需淘滩」；二是岁修时机——组织知识坚持冬季枯水统一岁修，部落知识主张秋汛后'
        '淤积严重须提前，后形成常规冬季加特殊提前的双轨机制；三是灌区扩展中官员主张修坝，'
        '与「无坝引水」传统原则冲突，工程多次受挫后回调。经实测验证与标准调整做知识整合，走向协同。\n'
        '【样例3·应输出】都江堰，三类知识，知识冲突，高阻尼，岁修争议，无坝引水，知识整合\n'
        '【样例3·为何这样抽】'
        '案例名后紧接框架总词「三类知识」，再是现象「知识冲突」「高阻尼」，'
        '再是具体争议与原则，最后「知识整合」收束；框架总词不可省。'
        '本卡三类只是冲突叙事中的角色，并未以「分别定义/区分每一类」为主体展开，故不必再拆出传统/组织/部落三词。\n'
        '【样例3·错误抽法（禁止再犯）】'
        '都江堰，知识冲突，高阻尼，岁修争议，无坝引水，知识整合——缺靠前的框架总词「三类知识」。\n'
        '\n'
        '【样例4·摘要】工程本体三类知识：以60问展开传统/组织/部落三类知识的定义、联系、区别与协同；'
        '传统为显性低维、组织为半显性中维、部落为隐性高维，AI助力部落知识显性化。'
        '提出低阻尼振荡体系（统一语义、边界明确、技术赋能、动态迭代），并用除乘加、DMT、四色法、'
        '邻接矩阵等工具支撑；特强调邻接矩阵量化知识直接与深层关联。'
        '辅以都江堰与教育/软件工程案例，以及知识度量（荣格同时性、唯识宗等）与思维转换路径，'
        '区分哲学本体与工程本体，落向知识治理与组织能力提升。\n'
        '【样例4·应输出】三类知识，传统知识，组织知识，部落知识，工程本体论，低阻尼振荡，统一语义，知识度量，邻接矩阵，都江堰\n'
        '【样例4·为何这样抽】'
        '①主体是「三类知识」框架，总词居首；'
        '②正文分别定义并区分传统/组织/部落每一类，须紧随总词把三类分项都抽出，不可只留总名；'
        '③工程本体论、低阻尼振荡、统一语义、知识度量是理论定位与机制路径；'
        '④邻接矩阵虽是工具细节，但是文中强调的量化手段，应靠后纳入；'
        '⑤都江堰是验证案例，非理论主体，靠后。\n'
        '【样例4·错误抽法（禁止再犯）】'
        '三类知识，工程本体论，低阻尼振荡，统一语义，知识显性化，知识度量，都江堰——'
        '有总词却漏掉正文已分别展开的「传统知识、组织知识、部落知识」（若正文只主要讨论三类知识中某一种，则语义关键词只需抽出该种知识）；'
        '或把并列工具全堆上而漏掉被强调的「邻接矩阵」。\n'
        '\n'
        '【样例5·摘要】W15体联IV主题课设19组公能批改报告：以除乘加为本体轴心评估四链节'
        '（除乘加/双O/Issue/蛙鸣），诊断「两张皮」（底层技术与体联业务脱节）；'
        '知识建议明确把除法指向「复杂健康映射为三时」、乘法指向「Chronos/Kairos 融合精准PSI」、'
        '加法落实电量不足回滚休眠等体联内涵；并指向组型进化。\n'
        '【样例5·应输出】体联IV，体联除乘加，三时，精准PSI，Chronos，Kairos，公能批改，两张皮，双O目标\n'
        '【样例5·为何这样抽】'
        '①「体联IV」是标题与正文锚定的主题内容主体，绝不是可降权的「应用场景」——必须居前；'
        '②通用框架「除乘加」须落到主题上写成「体联除乘加」，否则发虚、看不出在批什么；'
        '③正文已点名的内涵词「三时」「精准PSI」「Chronos」「Kairos」是 D 层具体内容，必须抽出，'
        '不能只剩「公能批改/四链节/蛙鸣涌现」等过程壳；'
        '④「公能批改」是本卡文类/评价框架，重要性高于后续诊断分面，放在内涵词之后、「两张皮」之前较合适；'
        '「两张皮」「双O目标」是诊断与手段分面（M），靠后；'
        '整体约 5:3:2，一眼能看出：体联课设 + 除乘加内涵 + 公能诊断。\n'
        '【样例5·错误抽法（禁止再犯）】'
        '公能批改，除乘加分析，四链节，两张皮，双O目标，Issue链，蛙鸣涌现，组型进化——'
        '全是过程/评价壳，漏掉主题「体联」与内涵「三时/精准PSI/Chronos/Kairos」；'
        '并把主题误判为「仅应用场景」而主动降权。一眼不知卡片在具体讲什么。\n'
        '\n'
        '【样例6·摘要】都江堰三级筛分作为熵减装置：鱼嘴一筛（四六分水离心分离）、'
        '飞沙堰二筛（超量漫顶甩沙）、宝瓶口三筛（定量纯化）；关键不在对抗熵增，'
        '而在借势（重力/离心力等）把自发熵增转为局部熵减通道——外江作熵增区、内江作熵减区；'
        '启示数智组织设计熵增承载与熵减工作的分离，并以「深淘滩低作堰」维护熵减能力。\n'
        '【样例6·应输出】都江堰，熵增区，熵减区，借势治水，三级筛分，鱼嘴一筛，飞沙堰二筛，宝瓶口三筛\n'
        '【样例6·为何这样抽】'
        '①主体「都江堰」居首；'
        '②「熵增区/熵减区」是作者立住的具体空间划分（D/M 交界的可指认对象），优于空喊「分离机制」；'
        '③「借势治水」点出「不对抗、借自然规律」的核心主张，仍具体可读；'
        '④「三级筛分」+「鱼嘴一筛/飞沙堰二筛/宝瓶口三筛」把工程路径具名摊开——'
        '这才是「不多不少」代表本卡内容；'
        '⑤禁止把具名三级工程压成「熵增熵减转化」「分离机制」等云雾概括（那叫假深刻）。\n'
        '【样例6·错误抽法（禁止再犯）】'
        '都江堰，分离机制，熵增熵减转化，四六分水，熵增承载区，数智组织——'
        '把鱼嘴/飞沙堰/宝瓶口与熵增区/熵减区等具体主体挤掉，只剩发虚的机制元词；'
        '一眼只有「好像在讲转化」，猜不出本卡的工程与空间划分。\n'
        '\n'
        '【从样例抽出的硬规则】'
        '①专名/主题/内容主体居前且不可被复合词吞没；主题不是「场景」可降权项；'
        '②通用框架词须带上主题定语落到本卡（如除乘加→体联除乘加），勿只留通用壳；'
        '③D/M/T 三层都要有：D=具体内容主体（专名、实体、内涵概念），'
        'M=手段/过程/方法/框架，T=放眼启示/落点（同样是有所指的具体概念，不是漂亮但空的归纳标签）；比重约 5:3:2；'
        '④正文已点名的具体内涵/具名实体优先于云雾概括词'
        '（禁用「分离机制」「熵增熵减转化」「推进链条」等占满名额而挤掉具象词）；'
        '⑤「深刻」≠更抽象；深度说法优先于高频表面说法，但仍须具体可读；'
        '⑥禁看不懂硬捏词、禁过大元词与重复上位理论词占位；'
        '也不用「研究」「方法」「分析」等无区分度泛词'
        '（单独出现或作空壳后缀皆忌，须落到本卡具体对象）；'
        '⑦checking 须做一眼可读自检与语义段覆盖自检，并合理增/删/改/换序，不要只改措辞；'
        '⑧出现「三大刻度」「三类知识」「两类策略」等框架总词时可抽出总词；'
        '若正文对成员分项有明确分别解释且各有一定篇幅，须紧随总词列出具体是哪几个，顺序按文段侧重；'
        '若只主要展开其中某几个、其余未提或仅一笔带过，则只跟展开到位的那些，勿机械凑齐全套；'
        '分项仅作叙事角色、未作主体展开时，可只保留总词；'
        '⑨文中被强调的具体工具/方法/工程分节可纳入，勿因「太细」一律删光去换空壳机制词；'
        '⑩慎取文末归纳口号收束词：'
        '若某词只是结尾的概括性结论，一眼看不出具体指什么，且并非开头问题与主体论证在立的对象，'
        '应换成论证里真正在讲的内容主体词。'
        '例如：“三维最优解”这种，不如“组织协同”“集体目标”更能代表实际内容；'
        '⑪无论篇幅长短，须覆盖各语义段（按话题/论证单元划分，非自然段）的内容语义，勿整段遗漏。\n'
    )


def build_keyword_extraction_instruction(
    max_keywords: int,
    with_candidates: bool = False,
    min_keywords: Optional[int] = None,
    *,
    hard_cap: int = CARD_KEYWORDS_HARD_CAP,
) -> str:
    candidate_hint = (
        '如果备选集合中有合适的语义关键词，请优先直接选取（同样须满足下列规范）；'
        '若备选词过长、不够原子、有歧义、表意不清或理解偏浅，请自行凝练为自然合规的语义词，禁止机械截断。'
        '特别注意：备选里若出现标题/专名/项目名等「主体锚点」词，不得因排序靠后就草率筛掉——'
        '须先判断它是否就是本卡片主体身份；若是，应进入前列，而不是在精简时被挤掉或被更长复合词吞掉。'
        if with_candidates else ''
    )
    lo = min_keywords if min_keywords is not None else max(1, min(2, max_keywords))
    if lo > max_keywords:
        lo = max_keywords
    preferred = max_keywords
    count_hint = (
        '【数量】以「合适」为准，不要纠结凑满或卡死某一个数字；'
        f'通常可参考 {lo}～{preferred} 个，按层次与语义段覆盖需要增减；'
        f'本卡建议最好不超过 {preferred} 个，硬上限 {hard_cap} 个（必要时可到 {hard_cap}，不要无故顶满）。'
        '字数更长时允许更多词以覆盖各语义段，但仍以不多不少为代表；'
        '层次清楚、主张面多时宁可略多一点把中层与语义段补齐，也不要因控数而砍掉主体锚点或关键机制/框架词；'
        '主题单一、层次扁平时宁少勿滥。\n'
    )
    return (
        '你是擅长阅读理解文本并提炼**语义关键词**的专家。\n'
        '【什么是关键词】关键词是用于表达文字主体内容的核心词汇或短语（不可以是短句）。\n'
        '【语义关键词】不是空泛标签，而是能刻画本卡片具体语义内容的词/短语——'
        '每个词都必须在说这张卡片里真实存在的知识对象、概念、主张或做法。\n'
        '【质量总原则】完整而准确、简单而深刻：既覆盖主体内容，又抓住作者真正想立住的点；'
        '词频与字面表述只是基础信号，不可压过文字背后的意图与更深一层的准确说法。'
        '但「深刻」绝不是「更抽象」：禁止用发虚的元机制词替换正文已有的具体主题与具名内涵。\n'
        '【一眼可读 + D/M/T】抽出的词合在一起，须让人一眼明白这张卡具体在讲什么。'
        '区分两类：'
        '（1）具体内容主体——主题/专名/实体/内涵概念（如体联、三时、精准PSI、鱼嘴、熵增区）；'
        '（2）手段或周边信息——评价框架、过程链节、方法壳、启示落点（如公能批改、四链节、分离机制）。'
        '二者都要，但主体内容必须占优。按 D/M/T 审视：'
        'D=立足的具体内容主体，M=面向的手段/过程/方法，T=放眼的启示/落点；'
        '三层缺一不可，比重大约 5:3:2（指语义比重，非硬凑个数）。'
        '若整盘几乎都是 M/T 壳词、D 层空洞——必须增补具体内涵词并降权/删除云雾概括。'
        '无论篇幅长短，还须覆盖各语义段（按话题/论证单元划分，不是印刷上的自然段）的内容语义，不要有整段遗漏。\n'
        '【关键词常见特点规范】\n'
        '1. 应尽量属于名词体系或名词性短语；通常不用谓语动词（以免变成短句）。'
        '个别情况可用名词化后的动词，且必须是短语而不是短句。\n'
        '2. 按重要性排序：越靠前越重要、越顶级、越核心、概念范围越大。'
        '典型层次（按卡片实际取舍，不必硬凑）：'
        '主题/专名/内容主体（标题与正文锚定的项目、案例、课设主题）→ '
        '落到本卡的框架词（通用框架须带主题/定语；如「纸联除乘加」「三大刻度」等有效总词）→ '
        '正文点名且展开到位的具体内涵/成员分项（有分别解释且有至少一小段篇幅的才跟；一笔带过的不跟；顺序按文段侧重）→ '
        '手段或诊断（M）→ 启示/落点（T）。'
        '标题主题绝不可被当成「仅应用场景」而降权删掉；'
        '缺具体内涵（只剩过程壳）与缺中层（只有总名+散点）都是常见失误。\n'
        '3. 必须原子化：一词一事。例如「医学本体落地」应拆为「医学本体」「组织落地」等。'
        '禁止为「省名额」把两个半生不熟的概念硬捏成让人看不懂的复合词。\n'
        '4. 不可有歧义潜在可能。例如「可扩展性本质」既可理解为找原因也可理解为陈述结果，不可取。'
        '表意模糊、读者难一眼看懂的词也不取。\n'
        '5. 应覆盖文字主要内容；可参考词频但绝不能只看词频。'
        '必须真正理解文字语义并通透揣摩作者视角与意图，'
        '使作者本人也会认同所选语义关键词及其顺序就是自己所想。'
        '若高频字面词偏浅、而文中另有更准更深刻的说法（或作者真正要立的价值点），应取后者；'
        '若「更深刻」的候选其实是空壳抽象、而正文已有具名实体/内涵，应取具名具体说法。\n'
        '6. 慎取过大、过空、优先级其实不高的元概念词（即便文中出现过）：'
        '若它不是本卡独特贡献或作者主推点，应降权或去掉。'
        '尤其警惕「研究」「发展」「分析」等无区分度泛词'
        '（单独出现或作空壳后缀皆忌，须落到本卡具体对象），'
        '以及「分离机制」「熵增熵减转化」「推进链条」「四链节」等占满名额。\n'
        '7. 避免「重复占位」：若已有更具体、更能代表本卡的项目/案例框架词，'
        '不要再并列一个更上位、对本卡贡献不大的同族理论词来占名额。\n'
        f'{count_hint}'
        '这几个语义关键词共同形成的语义空间，必须基本上能够代表整张卡片：'
        '覆盖广度、深度与内容具体性兼顾；不多不少地代表本卡内容；'
        '重视完整性、层次性、有总有分、有 D 有 M 有 T；'
        '必须有具体实在的知识内容（如「共享单车」「看门狗回滚」「DMT微版面」「三时」「鱼嘴一筛」），'
        '禁止「认知协同」「深度思考」「综合能力」「分离机制」等模糊不清或发虚占位的词。\n'
        f'{_reflective_pitfall_examples()}'
        f'{candidate_hint}\n'
        f'【字数】每个中文语义关键词尽量具体准确且不超过 {KEYWORD_MAX_CN_CHARS} 个汉字；'
        f'英文每个词不超过 {KEYWORD_MAX_EN_CHARS} 个字符。'
        '系统不会事后硬截断，请你自行凝练，禁止僵硬截断。'
        '专名/公式缩写（如 PSI、Chronos、Kairos）可保留通行写法。\n'
        '【工作流程——禁止直接甩最终结果】\n'
        '（A）先理解文字语义：拆解结构、读通主旨、揣摩作者视角与意图；'
        '同时兼顾标题/专名、词频等表层信号。'
        '理解阶段须明确列出：'
        '本卡「具体内容主体」是什么（主题/专名/内涵，不是评价壳）；'
        '有哪些语义段（话题/论证单元）须被覆盖；'
        '哪些是手段/周边；主要层次；作者真正想立住的点；'
        '并预估 D/M/T 各占什么（约 5:3:2）。'
        '（区分：高频表面说法 vs 更深但须仍具体的准确说法）。\n'
        '（B）给出第一版语义关键词（可带简要理由）。\n'
        '（C）审核（checking）——顺序强制如下，不可跳过：\n'
        '  C1. 先审「理解」本身：是否完整而准确？是否简单而深刻？'
        '有无把主题误判成「仅场景」？有无把「深刻」理解成「更抽象」？'
        '有无漏掉标题/专名等最显眼的内容主体？'
        '有无把偏浅的高频说法当成了核心？有无理解偏了或层次缺块？'
        '理解有问题则先修正理解，再谈关键词。\n'
        '  C2. 再审「关键词集合」相对理解：是否需要增、删、改、换序'
        '（不只是改措辞）？尤其检查：'
        '一眼可读——外人能否猜出本卡具体在讲什么？'
        '各语义段是否都有代表词、有无整段遗漏？'
        '主题/专名是否在前列且未被复合词吞掉；'
        '通用框架是否已落到本卡主题（如体联除乘加）；'
        '正文点名且展开到位的具体内涵/成员分项是否紧随总词、是否必要却被挤掉、有无一笔带过却硬凑齐全套；'
        'D/M/T 是否缺层、是否几乎全是发虚 M/T；'
        '过大过空或云雾机制词、「研究/方法/分析」类无区分度泛词是否该删；'
        '文末归纳口号（非全文主体概念）是否占了本该给「开头主问/类比论证对象」的名额'
        '——应换成论证里真正在讲的可指认概念（例如组织协同、集体目标这种清晰概念）；'
        '表意不清的硬捏词是否该拆或换；偏浅词是否该换成更准更具体的说法。\n'
        '  C3. 最后对留下的每个词逐条按规范审核（名词性/顺序/原子化/无歧义/作者意图一致等）。\n'
        '形成第二版语义关键词作为最终输出。\n'
        '（D）最终输出：先单独一行输出标记 '
        f'{SEMANTIC_KEYWORDS_FINAL_MARKER} ，下一行仅输出最终语义关键词列表：'
        '中文逗号分隔，无其它文字。\n'
        f'示例最终段：\n{SEMANTIC_KEYWORDS_FINAL_MARKER}\n共享单车，看门狗回滚，DMT微版面\n'
    )


def has_final_marker(
    raw_text: str,
    markers: Optional[Tuple[str, ...]] = None,
) -> bool:
    """检查输出是否含约定的最终结果标记（如 [FINAL]）。"""
    text = str(raw_text or '')
    if not text.strip():
        return False
    for m in (markers or DEFAULT_FINAL_MARKERS):
        if m and m in text:
            return True
    return False


def is_rejected_semantic_keyword(keyword: str) -> bool:
    """
    抽词验收失败条件（按用户约定）：
    - 汉字数 ≥ SEMANTIC_KEYWORD_REJECT_MIN_CN_CHARS（默认 10；英文字母与数字不计）
    - 或含有反引号 `
    （允许英文句点 .，如「软件3.0」）
    """
    kw = str(keyword or '').strip()
    if not kw:
        return True
    if count_cn_chars(kw) >= SEMANTIC_KEYWORD_REJECT_MIN_CN_CHARS:
        return True
    if '`' in kw:
        return True
    return False


def find_rejected_semantic_keywords(keywords: List[str]) -> List[str]:
    """返回本批中不合格的关键词（保持出现顺序、去重）。"""
    bad: List[str] = []
    seen = set()
    for kw in keywords or []:
        k = str(kw or '').strip()
        if not k or k in seen:
            continue
        if is_rejected_semantic_keyword(k):
            seen.add(k)
            bad.append(k)
    return bad


def parse_final_semantic_keywords(
    raw_text: str,
    *,
    max_count: Optional[int] = None,
    require_marker: bool = False,
) -> str:
    """从模型完整输出中解析 [FINAL] 之后的语义关键词。

    require_marker=True 时若无标记则抛 ValueError（供调用失败重试）；
    默认 False 时无标记则回退全文归一化（兼容旧路径）。
    """
    text = str(raw_text or '')
    marker = SEMANTIC_KEYWORDS_FINAL_MARKER
    idx = text.rfind(marker)
    if idx < 0:
        # 兼容旧标记
        alt = SEMANTIC_KEYWORDS_FINAL_MARKER_ALT
        idx_alt = text.rfind(alt)
        if idx_alt >= 0:
            marker = alt
            idx = idx_alt
    if idx >= 0:
        after = text[idx + len(marker):].strip()
        # 取标记后第一段非空内容（到空行或结束）
        lines = [ln.strip() for ln in after.splitlines() if ln.strip()]
        payload = lines[0] if lines else after
        # 去掉可能的代码围栏
        payload = re.sub(r'^```\w*\s*|\s*```$', '', payload).strip()
        return normalize_semantic_keywords(payload, max_count=max_count)
    if require_marker:
        raise ValueError(f'输出缺少最终标记 {SEMANTIC_KEYWORDS_FINAL_MARKER}')
    return normalize_semantic_keywords(text, max_count=max_count)


def clean_semantic_keyword_token(keyword: str) -> str:
    """清洗单个语义关键词：去引号/前缀/空白，不做字数硬截断。"""
    kw = re.sub(r'^[「"\']+|[」"\']+$', '', str(keyword or '').strip())
    kw = re.sub(r'^(语义关键词|关键词|词)[\d]*[:：\s]*', '', kw, flags=re.I).strip()
    kw = re.sub(r'\s+', '', kw)
    return kw


def trim_keyword_length(keyword: str, max_cn_chars: int = KEYWORD_MAX_CN_CHARS) -> str:
    """
    兼容旧调用：仅做清洗，不再按字数硬截断。
    字数约束应在抽取 prompt 中约束模型自然生成。
    """
    return clean_semantic_keyword_token(keyword)


def _is_mostly_english(text: str) -> bool:
    letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return letters >= max(1, len(text) // 2)


def normalize_semantic_keywords(
    keywords_text: str,
    max_cn_chars: int = KEYWORD_MAX_CN_CHARS,
    *,
    max_count: Optional[int] = None,
) -> str:
    """
    归一化为顿号/逗号分隔的语义关键词串。
    只做拆分、去杂质、去重；**不对超长词做代码硬截断**（max_cn_chars 保留仅为兼容旧调用签名）。
    """
    _ = max_cn_chars  # 不再用于硬截断
    parts = re.split(r'[,，;；、/\n\r\t]+', str(keywords_text or ''))
    normalized: List[str] = []
    for raw in parts:
        kw = clean_semantic_keyword_token(raw)
        if kw and kw not in normalized:
            normalized.append(kw)
            if max_count is not None and len(normalized) >= max_count:
                break
    return '，'.join(normalized)


def split_semantic_keywords_raw(keywords_text: str) -> List[str]:
    """拆分模型输出的关键词列表，不做长度截断（语义梳理专用）。"""
    parts = re.split(r'[,，;；\n]', str(keywords_text or ''))
    result: List[str] = []
    for raw in parts:
        kw = re.sub(r'^[「"\']+|[」"\']+$', '', str(raw or '').strip())
        kw = re.sub(r'^(关键词|词)[\d]*[:：\s]*', '', kw, flags=re.I).strip()
        if kw and kw not in result:
            result.append(kw)
    return result


def count_cn_chars(text: str) -> int:
    return sum(1 for ch in (text or '') if '\u4e00' <= ch <= '\u9fff')


def is_semantic_keyword_length_valid(keyword: str, max_cn_chars: int = KEYWORD_MAX_CN_CHARS) -> bool:
    """判断关键词是否满足字数上限（语义梳理：禁止后处理硬截断，只接受自然合规词）。"""
    kw = (keyword or '').strip()
    if not kw:
        return False
    if _is_mostly_english(kw):
        words = kw.split()
        token = words[0] if words else kw
        return 0 < len(token) <= KEYWORD_MAX_EN_CHARS
    return count_cn_chars(kw) <= max_cn_chars


def parse_llm_color_dmt_response(text: str) -> Tuple[str, str]:
    """从 LLM 返回中解析四色(R/B/P/G)与 DMT(D/M/T)，容忍多余说明文字。"""
    raw = (text or '').strip().upper()
    if not raw:
        return '', ''

    compact = re.sub(r'[^RBPGDMT]', '', raw)
    if len(compact) >= 2:
        fc = compact[0] if compact[0] in 'RBPG' else ''
        dmt = compact[1] if compact[1] in 'DMT' else ''
        if fc and dmt:
            return fc, dmt

    match = re.search(r'([RBPG])\s*[,/\s\-_]*\s*([DMT])', raw)
    if match:
        return match.group(1), match.group(2)

    fc = dmt = ''
    for ch in raw:
        if not fc and ch in 'RBPG':
            fc = ch
        elif not dmt and ch in 'DMT':
            dmt = ch
        if fc and dmt:
            break
    return fc, dmt


def parse_llm_single_color(text: str) -> str:
    raw = (text or '').strip().upper()
    for ch in raw:
        if ch in 'RBPG':
            return ch
    return ''


def parse_llm_single_dmt(text: str) -> str:
    raw = (text or '').strip().upper()
    for ch in raw:
        if ch in 'DMT':
            return ch
    return ''


def parse_knowledge_type(text: str) -> str:
    """Parse trad/org/trib from LLM output."""
    raw = (text or '').strip().lower()
    mapping = {
        'trad': 'trad', 'traditional': 'trad', '传统': 'trad', 't': 'trad',
        'org': 'org', 'organizational': 'org', '组织': 'org', 'o': 'org',
        'trib': 'trib', 'tribal': 'trib', '部落': 'trib', 'l': 'trib',
    }
    if raw in mapping:
        return mapping[raw]
    for token in re.split(r'[,|/\s]+', raw):
        token = token.strip().lower()
        if token in mapping:
            return mapping[token]
    return ''


def _strip_attr_output_line_prefix(line: str) -> str:
    """去掉列表符号/序号前缀，但绝不剥掉词名本身的前导数字（如 6字诀、271教育）。"""
    s = (line or '').strip()
    # markdown / bullet
    s = re.sub(r'^[\-\*•]+\s*', '', s)
    # 仅当「数字 + 序号分隔符」时去掉，如 "1. " / "12、" / "3) "
    # 注意：不能用 lstrip('0123456789...')，否则会把 6字诀、271 剥坏
    s = re.sub(r'^\d+[.\、\)]\s+', '', s)
    return s


def parse_batch_keyword_attributes(
    text: str,
    expected_keywords: List[str],
    final_marker: str = '【最终结果如下】',
) -> Dict[str, Dict[str, str]]:
    """Parse Claude batch output: 关键词|四色|DMT|三类知识 per line after final marker."""
    raw = text or ''
    if final_marker in raw:
        raw = raw.split(final_marker, 1)[1]
    result: Dict[str, Dict[str, str]] = {}
    expected_set = set(expected_keywords)
    # 按长度降序，便于前缀匹配（避免短词抢长词）
    expected_sorted = sorted(expected_set, key=len, reverse=True)

    for line in raw.splitlines():
        line = _strip_attr_output_line_prefix(line)
        if not line or '|' not in line:
            continue
        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 4:
            continue
        raw_kw = re.sub(r'\s*【.*?】\s*$', '', parts[0]).strip()
        kw = raw_kw if raw_kw in expected_set else ''
        if not kw:
            for e in expected_sorted:
                if raw_kw == e or raw_kw.startswith(e):
                    kw = e
                    break
        if not kw:
            continue
        fc, dmt, kt = parts[1].upper(), parts[2].upper(), parts[3].lower()
        fc = fc[0] if fc and fc[0] in 'RBPG' else parse_llm_single_color(fc)
        dmt = dmt[0] if dmt and dmt[0] in 'DMT' else parse_llm_single_dmt(dmt)
        kt = parse_knowledge_type(kt)
        entry: Dict[str, str] = {}
        if fc:
            entry['four_color_type'] = fc
        if dmt:
            entry['dmt_level'] = dmt
        if kt:
            entry['knowledge_type'] = kt
        if entry:
            result[kw] = entry
    return result


def extract_kimi_message_text(message: Any) -> str:
    """从 Kimi message 取可用文本：优先 content，空则 fallback reasoning_content。"""
    if message is None:
        return ''
    content = getattr(message, 'content', None)
    if content is not None and str(content).strip():
        return str(content).strip()
    reasoning = getattr(message, 'reasoning_content', None)
    if reasoning is not None and str(reasoning).strip():
        return str(reasoning).strip()
    return ''


def debug_log_kimi_response(tag: str, response: Any, raw_text: str = '', parsed: str = '') -> None:
    """打印 Kimi 完整响应细节，便于排查 content 为空 / 解析失败。"""
    print(f'[{tag}] === Kimi 原始响应调试 ===')
    if response is None:
        print('  response=None')
        return

    model = getattr(response, 'model', None)
    usage = getattr(response, 'usage', None)
    print(f'  model={model!r}')
    if usage is not None:
        print(
            f'  usage: prompt={getattr(usage, "prompt_tokens", None)} '
            f'completion={getattr(usage, "completion_tokens", None)} '
            f'total={getattr(usage, "total_tokens", None)}'
        )

    choices = getattr(response, 'choices', None) or []
    if not choices:
        print('  choices=[]')
        return

    for i, choice in enumerate(choices):
        finish = getattr(choice, 'finish_reason', None)
        msg = getattr(choice, 'message', None)
        content = getattr(msg, 'content', None) if msg else None
        reasoning = getattr(msg, 'reasoning_content', None) if msg else None
        refusal = getattr(msg, 'refusal', None) if msg else None
        print(f'  choice[{i}] finish_reason={finish!r}')
        print(f'  choice[{i}].message.content={content!r}')
        if reasoning:
            preview = str(reasoning)
            if len(preview) > 800:
                preview = preview[:800] + '...(truncated)'
            print(f'  choice[{i}].message.reasoning_content={preview!r}')
        if refusal:
            print(f'  choice[{i}].message.refusal={refusal!r}')

    print(f'  extract合并文本={raw_text!r}')
    if parsed != '':
        print(f'  解析结果={parsed!r}')
