"""Subject-specific prompt rule fragments for homework grading.

These fragments are nkcn adapters layered on top of the yq-aligned base prompts.
Keep schema and pass structure in ``prompts.py``; put scoring nuance here.
"""

from __future__ import annotations


COMMON_FINAL_INTENT_RULES = '''
【最终作答与微涂改通用规则】
注意学生可能有涂改，或用斜杠/横线划掉后在旁边、上方、右侧重新修正的情况；批改时以未被划掉、最终保留的手写内容为准。'''


CHINESE_SLASH_TIANZIGE_RULES = '''
【语文手写涂改 / 斜杠划掉 / 田字格】
1. 斜杠删除线多为从左上到右下方向的斜线(也不排除其他可能)；被杠掉的部分可能是偏旁/部首、单个字或多个字，以图像实际划线范围为准，被杠掉即作废。
2. 「读拼音写词」常用田字格；学生涂改或斜杠修正后的最终字，常写在田字格外（格子上/下/左/右、格缝旁），仍应计入最终作答。
3. 转写 student_answer / visual_answer 时，只写最终保留、未被划掉的有效手写；若格内被斜杠划掉而在格外重写，以格外的修正字为准。'''


COMMON_DETECT_LAYOUT_RULES = '''
【分栏/双栏版面归属】
1. 页面为左右双栏时，阅读顺序通常先左栏自上而下，再右栏自上而下；右栏顶部的 (2)(3) 等小题可能属于左栏底部刚开始的大题。
2. 当右栏小题只有「(2)…」但缺少大题背景时，应回看左栏下方或同页前序题号，填写正确的 parent_group_id 与 parent_stem_excerpt。
3. 不要因为小题跨栏、距离父题干较远，就把它编号为 auto-* 或当成独立题；能从同页前序大题推断父题时必须归属到该大题。'''


CHINESE_GRADE_RULES = '''
【语文专项批改规则】
1. 阅读理解、仿写、概括、表达理由类题，若阅读材料在本页可见且学生回答能围绕文本或生活经验自圆其说、言之有理，应判 correct；不要仅因「无唯一标准答案」设为 uncertain。
2. 这类题只有在材料缺失、回答离题、答非所问、关键依据明显错误或字迹大面积不可辨时，才判 wrong/partial/uncertain。
3. 对于「读拼音，写词语」「读拼音，结合语境写字词」「看拼音写词语」这类根据拼音写字词的题，需要额外关注学生最终保留手写词是否写成明显错别字；若写错，要在 error_type 写明「字形错误」或「错别字」。
4. 其它语文题按题意和答案内容批改，不需要刻意做汉字部件级字形审查。'''


CHINESE_SENTENCE_CONTRACTION_PAGE_RULES = '''
【本页含缩句题：句子主干专项核验（仅约束 correct_answer 与判分）】
1. 先从印刷原句独立提取句子主干，再比较各选项；不得因为学生选择了某项，就反向把该项解释为正确缩句。
2. 缩句可以删除定语、状语、补语等修饰限制成分，但必须保留主语中心语、全部核心谓语和必要宾语；不得把“主谓宾”误解为每句只保留一个谓语。
3. 同一主语支配两个或以上由“和、并、又、且、同时”等连接的并列核心动词时，这些动词共同承担谓语功能，缩句后必须全部保留，并保留表达并列关系所需的连接词；漏掉任一核心动词都不是完整主干。
4. 例如“探索精神，极大地震撼和鼓舞着人们”的主干是“精神震撼和鼓舞着人们”，不能缩成只含“鼓舞”的“精神鼓舞着人们”。
5. 本规则不得改写 student_answer：选择题括号内学生最终保留的黑笔字母必须按图转写；教师红笔圈改、浅色残影和正确选项只能用于判分，不能混入学生答案。'''


CHINESE_PRONUNCIATION_SELECTION_DETECT_RULES = '''
【“给加点字选择正确读音”题内作答槽位（仅该题型）】
1. 若题干要求“给加点字（或给加点的字）选择正确的读音”，保持整道题一个 questions 记录和原题 id，不得拆成多个题目。
2. 除题目总 position 外，必须额外输出 answer_slots；每个加点字一项，按页面阅读顺序排列。其它语文题不要输出 answer_slots。
3. 每个 answer_slots 项严格使用以下字段：
   - slot_id："<题目id>:<加点字>"；
   - target：对应的加点字；
   - slot_position：紧凑包围该字的全部候选拼音及学生黑色勾选标记；
   - candidate_regions：逐个候选拼音的印刷区域，每项为 {"label": "带声调拼音", "position": [x1,y1,x2,y2]}；
   - mark_position：只紧密包围学生黑色勾/圈选笔迹，允许与候选拼音重叠；
   - layout_confidence：该槽位坐标置信度（0–100）。
4. 所有坐标均相对整页归一化到 0–1000。candidate_regions 通常恰有两个候选；必须保留声调，候选标签和坐标一一对应。
5. 本阶段不得判断学生选择了哪个候选，不得输出 selected_answer，也不得按正确读音推测勾选位置；只做客观版面标记。'''


CHINESE_PRONUNCIATION_SELECTION_GRADE_RULES = '''
【本页含经坐标校验的读音选择槽位（仅约束客观转写）】
1. 题目一类记录中的 answer_slots 是无损版面阶段给出的定位证据：candidate_regions 是印刷候选读音及其区域，mark_position 是学生黑色勾选笔迹区域，slot_position 是该字完整候选组。
2. 必须按 target 顺序逐槽观察原图，结合 mark_position 与 candidate_regions 的空间重叠/落点，先确定学生实际勾选的印刷候选，再组成 student_answer。
3. 不得根据词语的正确读音反推学生选择，不得忽略声调，不得把相邻槽位的勾串位；槽位与原图明显冲突时设 uncertain。
4. student_answer 只输出按 target 顺序排列的纯拼音列表，例如 "wēng, fǔ, mái"；不得输出“嗡(wēng)√”、加点字、括号或勾号。'''


ENGLISH_PAGE15_VISUAL_TRANSCRIPTION_LOCK = '''
【英语 student_answer 视觉转写锁（最高优先级）】
0. 必须先暂时忽略题意、上下文、语法、词义、词库、示例、正确答案和常见搭配，只观察学生最终保留的黑色或近黑色笔迹，逐字符转写 student_answer；转写完成后立即冻结，后续理解与判分不得回头补写、删改或替换任何字符。
0.1 禁止根据语法或语义知识脑补学生没有写出的字母、词尾、单词或选项。黑笔只写出词干时就保留词干，不得擅自补成现在分词、第三人称单数、复数、过去式或规范拼写；即使补全后才符合语境，也只能把规范形式写入 correct_answer。
0.2 选择题必须只按括号、横线或勾选槽位中的最终黑笔字母/标记转写。即使依据短文或语法可以确定另一选项才正确，student_answer 仍必须保留图中黑笔选择；正确选项只能写入 correct_answer，并据二者冲突判 wrong。
0.3 学生先写后划掉的英文视为作废，只保留未被划掉的最终黑笔内容；教师红笔订正、红笔删除线、去红后的淡色或断续残影均不得加入 student_answer。
0.4 英语宽容规则只允许影响 verdict 和 error_type，绝无权限把 student_answer 规范化。若题目明确考查特定词形、拼写或选项，缺少必要词尾/字母或选错选项不是可忽略的轻微瑕疵，须按冻结转写与 correct_answer 的实际差异判分。'''


ENGLISH_PARENTHESIZED_CHOICE_SLOT_GRADE_RULES = '''
【本页含经固定样例校验的英语括号选择槽位（最高优先级）】
1. 题目清单中 slot_type=parenthesized_choice 的 answer_slots 是无损版面证据：slot_position 紧凑包围作答括号，mark_position 只包围括号内学生最终保留的黑色手写字母，candidate_regions 仅给出本题印刷候选 A/B 的位置。
2. 完整页图后附有按题号标明的局部放大 ROI。必须逐题优先观察对应 ROI 的 mark_position，只转写其中实际可见的单个黑笔字母；不得把 candidate_regions 中的印刷 A/B 当成学生笔迹。
3. 先把 ROI 读到的字母原样写入并冻结 student_answer，再独立理解短文、生成 correct_answer 和 verdict。即使短文语义明确支持另一个选项，也绝不允许把正确选项反写为 student_answer。
4. answer_slots 不预填 selected_answer；若其中存在 observed_label，它来自不含题干和选项语义的独立 ROI-only 视觉转写，并已通过本地固定样例门禁，必须原样作为 student_answer。不得声称槽位“证明正确答案”。若局部黑笔确实不可辨，student_answer 写 "?" 并降低 recognition_confidence，禁止用语法或语义消除视觉不确定性。'''


ENGLISH_GRADE_RULES = '''
【英语专项批改规则】
0. 听力题源锁优先：题干含 Listen/listening/听力/听录音/听短文/听对话，且图像中没有音频、听力原文或录音材料时，必须 verdict=uncertain；不得因为表格栏目、常识或猜测把听力题判 correct/wrong。
1. 表格填写、仿照示例问答、角色扮演、信息整理类题，优先判断交际意图和栏目语义是否匹配；若答案能表达题目要求的信息，可判 correct。
2. 非拼写专项题中，轻微拼写、大小写、单复数或语法瑕疵但不影响理解时，不要直接判 wrong 或 uncertain；可在 error_type 为空或轻描淡写说明。
3. 只有听力依赖音频、关键信息材料确实不在图像中、长篇自由写作无明确评价依据、或学生答案严重不可辨时，才设为 uncertain。
4. 若题目给出词库/示例/表格栏目，材料已经足够判断，不要以「缺少对话原文/来源文本」为由设为 uncertain。
5. 家庭成员职业/地点/才能等调查表格通常没有唯一标准答案；只要 Who/What/Where 或人物/才能等栏目对应关系合理，driver/worker/postman/cook/sing 等信息可理解，就判 correct。类似 station 写成 staicion、movie 写成 movid、place/station 拼写不规范但语义仍可辨时，不作为 wrong 理由。'''


CHINESE_REVIEW_RULES = '''
【语文复核重点】
1. 对「读拼音，写词语」「读拼音，结合语境写字词」「看拼音写词语」这类根据拼音写字词的题，先从图像中重新转写学生最终保留的手写字，不要直接相信 student_answer；再检查是否明显写成错别字。
2. 仅当明显错别字（缺偏旁、写成另一常用字、整词与拼音/语境明显不符）时，才 ok=false，fix.verdict 设为 wrong 或 partial，并在 fix.error_type 写明「字形错误」或「错别字」。
3. 注意涂改、斜杠划掉后在上方/旁边/田字格外修正等情况：斜杠多为左上→右下，被杠掉的可能是部首或一字或多字等等；田字格题修正字常在格外，以未划掉的最终保留内容为准；若修正后字词正确，必须 ok=true，不得改判。
4. 笔迹略糊、结构略挤但可辨认是目标字时，保持 correct；无法确定时 ok=true，不要矫枉过正。
5. 对阅读理解和表达理由题，若答案言之有理且材料可见，可把原 uncertain 修正为 correct。'''


ENGLISH_REVIEW_RULES = '''
【英语复核重点】
0. 听力源锁优先：若题干含 Listen/listening/听力/听录音/听短文/听对话，且图像中没有音频或听力原文，不得把原 uncertain 改成 correct/wrong/partial；必须保持无法判断。
1. 表格、问答、仿写类题若答案能表达栏目要求的信息，可把原 uncertain 修正为 correct。
2. 表格调查题通常没有唯一标准答案；若人物/职业/地点/才能栏目关系合理，不要要求额外来源文本。
3. 非拼写专项中轻微拼写或语法问题不作为 wrong/uncertain 理由；例如 station 写成 staicion、movie 写成 movid 但语义可辨，应判 correct。只有无法理解或材料确实缺失时才保留 uncertain/wrong。'''


MATH_GRADE_RULES = '''
【数学评分细则】
1. 先结合题目真实要求、学生最终手写和参考答案判断，不要只看数值等价，也不要因为题干出现“多少/单位/过程”等词就自动降分。
2. 所有应用题大题（非填空题）均要检查最终答话：学生只有算式、数字、式子或中间过程，缺少最终答话时，通常不应判 correct。即使小题要求“用含有字母的式子表示”“结果各是多少”等，只要它隶属于应用题大题且不是填空题，也适用本规则；但独立填空、看图填空、表格填空、公式填空、括号内填空等填空式题目，以及口算、化简、选择或判断题不因缺答话扣分。
3. 必须先读取题目清单中的 final_unit_requirement，并严格区分“计算过程”和“答：……”两个区域：
   - required：普通应用题的最终答话需有与题意兼容的单位；缺单位通常 partial，单位不兼容通常 wrong。
   - forbidden：典型为“当 x=...时”代入求式子的值，仅表示含字母式子代入求值时，计算过程末值必须写成纯数，不得在该数值后加括号单位；数值正确但过程末值加了单位通常 partial。它绝不禁止“答：……”中的单位、量词或“倍”等关系词；最终答话中的数量仍须写与题意兼容的单位，例如过程写“=300”，答话写“平均每月生产300个”。
   - optional：单位不是本题评分点，加或不加都不单独扣分。
   若题型本身只填数字，或单位已在括号/表头中给出，通常为 optional，不因学生未重复写单位扣分。
   识别涂改时只保留学生最终有效笔迹：若计算结果后的“(米)”等括号单位已被横线、斜线或涂抹明确删除，student_answer 只转写保留下来的数值，不得把被删除单位用于扣分。
4. 只要学生最终答案是代数表达式，必须先独立化简/规范化，检查是否仍有可完成的常数运算或可合并同类项；不得把学生未化简式原样抄入 correct_answer 后直接判 correct。随后结合题型决定最终形式是否属于评分点：
   - 题目求最终数量、差、和、结果，或要求填写最终答案时，应给出与当前学段相符的规范化结果。例如“上午比下午多卖多少元”中，50a-30a 应化简为 20a；思路正确但未化简通常判 partial，correct_answer 填 20a，error_type 填 final_form_required。
   - 题目要求“列式”或“用含有字母的式子表示”时，只要式子准确表达数量关系，不强制展开、因式分解或改变结构；如 3(b+50)、12(a-b)、(m-n)÷5 可保持原形式。
   - 题目明确要求“化简/最简/约分/展开/因式分解/指定形式”时，必须满足该形式；等值但未达到要求的答案通常判 partial。
5. 题目要求“用指定方法/写出过程/运算律或性质名称”时，过程、方法或术语完整性属于评分点；若题目只问结果，不强行要求过程或术语。'''


MATH_OPERATION_LAW_FULL_NAME_GRADE_RULES = '''
【本页含运算律名称填空：完整术语专项核验】
1. 本规则只用于要求填写、判断或说明“运用了什么律/运算律/性质名称”的小题；只要求写字母公式、变形算式或计算结果的题不适用。
2. correct_answer 必须使用由运算符和变形方式确定的规范完整名称：乘法题写“乘法交换律”或“乘法结合律”，加法题写“加法交换律”或“加法结合律”，不得把 correct_answer 缩写成“交换律”“结合律”“交换”“结合”。多个规律并列时可写“乘法交换律和乘法结合律”，或在不产生歧义时写“乘法交换律和结合律”。
3. 学生只写“结合律/结合”或“交换律/交换”，缺少“乘法/加法”这一运算类别时，不得按同义、省略或结合题意视为完整正确；其余槽位正确时整题通常判 partial，error_type 写 operation_law_name_incomplete。
4. 必须区分学生手写与题干印刷字。若空格后已印有“律”，学生在空内只写“结合”，页面拼接后虽显示“结合律”，仍缺少“乘法/加法”；不得把印刷的“律”当成学生多写了一字，更不得替学生补出“乘法/加法”。
5. 例如“35×125×8 可以运用（ ）律，先算（ ）”：规范答案是“乘法结合律，125×8”。学生写“结合/结合律，125×8”时，第二空正确但第一空术语不完整，必须判 partial，不能判 correct。'''


MATH_DETECT_RULES = '''
【数学分栏题特别提醒】
1. 应用题/图形题的大题条件常在左栏底部，后续 (2)(3) 小题可能排在右栏顶部；右栏小题必须继承左栏同一大题的 parent_group_id 与 parent_stem_excerpt。
2. 若同页已出现 N-1，随后出现「(2)当……」这类小题，应优先编号为 N-2，而不是 auto-*。
3. 对所有数学题都必须输出 is_application_major_problem。应用题大题（非填空题）及其子题填 true；看图填空、表格填空、公式填空、括号内填空（如“m=( )”“( )元”）即使有生活情境或图表条件也填 false；口算、化简、选择、判断、纯单位换算或纯表达式练习填 false。'''


def pass1_grade_subject_suffix(subject: str) -> str:
    subject = (subject or '').strip().lower()
    if subject == 'chinese':
        return COMMON_FINAL_INTENT_RULES + '\n' + CHINESE_GRADE_RULES + '\n' + CHINESE_SLASH_TIANZIGE_RULES
    if subject == 'english':
        return COMMON_FINAL_INTENT_RULES + '\n' + ENGLISH_GRADE_RULES
    if subject == 'math':
        return COMMON_FINAL_INTENT_RULES + '\n' + MATH_GRADE_RULES
    return COMMON_FINAL_INTENT_RULES


def pass1_detect_subject_suffix(subject: str) -> str:
    subject = (subject or '').strip().lower()
    suffix = COMMON_DETECT_LAYOUT_RULES
    if subject == 'chinese':
        suffix += '\n' + CHINESE_PRONUNCIATION_SELECTION_DETECT_RULES
    if subject == 'math':
        suffix += '\n' + MATH_DETECT_RULES
    return suffix


def pass1_review_subject_suffix(subject: str) -> str:
    subject = (subject or '').strip().lower()
    if subject == 'chinese':
        return COMMON_FINAL_INTENT_RULES + '\n' + CHINESE_REVIEW_RULES + '\n' + CHINESE_SLASH_TIANZIGE_RULES
    if subject == 'english':
        return COMMON_FINAL_INTENT_RULES + '\n' + ENGLISH_REVIEW_RULES
    if subject == 'math':
        return COMMON_FINAL_INTENT_RULES + '\n' + MATH_GRADE_RULES
    return COMMON_FINAL_INTENT_RULES
