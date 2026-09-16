# english-primary4-question 1.0.0

小学四年级作业/试卷题目；保持原题型条件，固定动作仍须源哈希门控。正文见resources.json。仅离线验证。

## english-grade-rules

【英语专项批改规则】
0. 听力题源锁优先：题干含 Listen/listening/听力/听录音/听短文/听对话，且图像中没有音频、听力原文或录音材料时，必须 verdict=uncertain；不得因为表格栏目、常识或猜测把听力题判 correct/wrong。
1. 表格填写、仿照示例问答、角色扮演、信息整理类题，优先判断交际意图和栏目语义是否匹配；若答案能表达题目要求的信息，可判 correct。
2. 非拼写专项题中，轻微拼写、大小写、单复数或语法瑕疵但不影响理解时，不要直接判 wrong 或 uncertain；可在 error_type 为空或轻描淡写说明。
3. 只有听力依赖音频、关键信息材料确实不在图像中、长篇自由写作无明确评价依据、或学生答案严重不可辨时，才设为 uncertain。
4. 若题目给出词库/示例/表格栏目，材料已经足够判断，不要以「缺少对话原文/来源文本」为由设为 uncertain。
5. 家庭成员职业/地点/才能等调查表格通常没有唯一标准答案；只要 Who/What/Where 或人物/才能等栏目对应关系合理，driver/worker/postman/cook/sing 等信息可理解，就判 correct。类似 station 写成 staicion、movie 写成 movid、place/station 拼写不规范但语义仍可辨时，不作为 wrong 理由。

## english-review-rules

【英语复核重点】
0. 听力源锁优先：若题干含 Listen/listening/听力/听录音/听短文/听对话，且图像中没有音频或听力原文，不得把原 uncertain 改成 correct/wrong/partial；必须保持无法判断。
1. 表格、问答、仿写类题若答案能表达栏目要求的信息，可把原 uncertain 修正为 correct。
2. 表格调查题通常没有唯一标准答案；若人物/职业/地点/才能栏目关系合理，不要要求额外来源文本。
3. 非拼写专项中轻微拼写或语法问题不作为 wrong/uncertain 理由；例如 station 写成 staicion、movie 写成 movid 但语义可辨，应判 correct。只有无法理解或材料确实缺失时才保留 uncertain/wrong。

## english-page15-visual-transcription-lock

【英语 student_answer 视觉转写锁（最高优先级）】
0. 必须先暂时忽略题意、上下文、语法、词义、词库、示例、正确答案和常见搭配，只观察学生最终保留的黑色或近黑色笔迹，逐字符转写 student_answer；转写完成后立即冻结，后续理解与判分不得回头补写、删改或替换任何字符。
0.1 禁止根据语法或语义知识脑补学生没有写出的字母、词尾、单词或选项。黑笔只写出词干时就保留词干，不得擅自补成现在分词、第三人称单数、复数、过去式或规范拼写；即使补全后才符合语境，也只能把规范形式写入 correct_answer。
0.2 选择题必须只按括号、横线或勾选槽位中的最终黑笔字母/标记转写。即使依据短文或语法可以确定另一选项才正确，student_answer 仍必须保留图中黑笔选择；正确选项只能写入 correct_answer，并据二者冲突判 wrong。
0.3 学生先写后划掉的英文视为作废，只保留未被划掉的最终黑笔内容；教师红笔订正、红笔删除线、去红后的淡色或断续残影均不得加入 student_answer。
0.4 英语宽容规则只允许影响 verdict 和 error_type，绝无权限把 student_answer 规范化。若题目明确考查特定词形、拼写或选项，缺少必要词尾/字母或选错选项不是可忽略的轻微瑕疵，须按冻结转写与 correct_answer 的实际差异判分。

## english-parenthesized-choice-slot-grade-rules

【本页含经固定样例校验的英语括号选择槽位（最高优先级）】
1. 题目清单中 slot_type=parenthesized_choice 的 answer_slots 是无损版面证据：slot_position 紧凑包围作答括号，mark_position 只包围括号内学生最终保留的黑色手写字母，candidate_regions 仅给出本题印刷候选 A/B 的位置。
2. 完整页图后附有按题号标明的局部放大 ROI。必须逐题优先观察对应 ROI 的 mark_position，只转写其中实际可见的单个黑笔字母；不得把 candidate_regions 中的印刷 A/B 当成学生笔迹。
3. 先把 ROI 读到的字母原样写入并冻结 student_answer，再独立理解短文、生成 correct_answer 和 verdict。即使短文语义明确支持另一个选项，也绝不允许把正确选项反写为 student_answer。
4. answer_slots 不预填 selected_answer；若其中存在 observed_label，它来自不含题干和选项语义的独立 ROI-only 视觉转写，并已通过本地固定样例门禁，必须原样作为 student_answer。不得声称槽位“证明正确答案”。若局部黑笔确实不可辨，student_answer 写 "?" 并降低 recognition_confidence，禁止用语法或语义消除视觉不确定性。

## -uncertain-rules[english]

【uncertain 触发条件（英语）】
以下情形必须将 verdict 设为 "uncertain"：
1. 听力题（题干含 Listen/听，答案依赖音频，图片无法提供）。
2. 口语/朗读/表演类任务。
3. 主观写作题（写信/写短文，无固定标准答案）。
4. 连线/图形匹配类操作题。
5. 学生答案严重模糊（≥50% 无法辨认）。

## -subject-hints[english]
按题型判断英语答案：拼写专项要逐词核查，表格/问答/仿写题优先看信息是否匹配；不要把印刷选项/印刷例句误当成学生作答。
