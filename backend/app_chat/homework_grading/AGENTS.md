# homework_grading/AGENTS.md

本文件适用于 `djangoProject/app_chat/homework_grading/` 下的连续图片批改/作业批改后端模块。还必须遵守仓库根目录 `AGENTS.md` 与 `djangoProject/AGENTS.md`。

## 模块定位

- 本目录是 nkcn 中“连续图片批改”作业批改链路的后端实现，承接 `/api/ci/*` 连续图片入口中的 `analysis_type='homework_grading'` 分流。
- 本模块负责单份 PDF 作业从预处理、逐页批改、跨页修补、学习阶段切分、错题记忆、L4 规则基线、L5 数字孪生体、整篇诊断、幻觉过滤、渲染批改图到结果读取的主链路。

## nkcn 文件职责

- `service.py`：nkcn 主编排。负责工作区、任务进度、Pass1 调度、Pass1.5、memory、session memory、profile、ontology、Pass2、幻觉过滤、渲染、结果组装。
- `preprocess.py`：PDF 渲染与清洁页面生成，保留去红笔能力。
- `prompts.py`：Pass1、Pass1.5、Pass2、L5/ontology 等 prompt 常量与构造函数；不得混入模型调用。
- `llm_clients.py`：Qwen/DeepSeek client、共享 JSON 解析、thinking 文本写入等底层模型工具。
- `grader_pass1.py`：Pass1 单页批改模型调用与 Pass1 JSON 归一化。
- `grader_pass1_5.py`：Pass1.5 跨页题修补模型调用。
- `grader_pass2.py`：Pass2 单产物收口、ontology→三区映射、逐题批语生成。
- `llm.py`：兼容导出层；新代码不要继续把 Pass1/Pass1.5/Pass2 逻辑塞回这里。
- `cross_page.py`：跨页题检测与修补。
- `sessions.py`：学习阶段切分、前序摘要、session memory 构建。
- `memory.py`：逐页结果汇总，`qid_global` 的统一出口。
- `profile.py`：L4 规则基线，作为 L5 数字孪生体的 baseline 证据；默认不作为对外并列画像落盘或展示。
- `ontology_builder.py`：L5 数字孪生体，产出 `student_ontology.json` 和必要审计。
- `hallucination_filter.py`：Pass1、Pass2、ontology 的幻觉检测、纠错、回写与审计。
- `render.py`：批改图渲染，含题目框、批改符号、全局题号角标、学习阶段横幅。
- `pass3.py`、`pass3_service.py`：双科交叉诊断。
- `curriculum.py`、`semantic_config.py`：课程标准树、标签白名单、中文术语映射、认知区域定义。
- `data/**`：三科课程标准树、英中术语映射、学科规则数据；属于功能输入，不是临时缓存。

## 主链路要求

新改动不得破坏以下链路顺序：

1. `preprocess_pdf`：PDF → `raw/` 与 `clean/` 页面图。
2. `build_pre_pass1_session_map`：Pass1 前学习阶段切分。
3. `grade_page`：Pass1 逐页批改（默认两阶段：全页 A → 跨页回填 parent_stem_excerpt → 各页 B；`HOMEWORK_PASS1_TWO_STAGE=0` 恢复单阶段），按 session 串行、阶段内并行。
4. `resolve_cross_pages`：Pass1.5 跨页题修补。
5. `verify_pass1_dir`：学科校验器回写不确定题和审计信息。
6. `build_memory` / `build_all_session_memories`：生成全局错题记忆与学习阶段记忆。
7. `build_student_profile`：生成 L4 规则基线，只供 L5 evidence / 降级排障使用。
8. `build_ontology`：生成 L5 数字孪生体，三区必须非空并保留兜底标记。
9. `analyze_pass2`：消费 ontology，生成整篇诊断、三区分类与逐题批语。
10. `run_hallucination_filter`：校验并必要时修正 Pass1、Pass2、ontology。
11. `render_page`：输出可视化批改页。
12. `get_homework_grading_result`：组装前端结果，兼容历史产物。

任何阶段失败都要有清晰错误、可查询状态或降级路径；不得静默吞掉导致前端显示“空成功”。

## 核心功能不得缺漏

以下能力属于连续图片批改核心功能。新增、重构或修复时不得擅自删减：

- 单 PDF 内部时序：`order_index` 升序代表学生作答时间先后。
- 学习阶段切分：使用“篇次/课时级学习阶段，低层栏目作为子模块”的口径；新产物只写 `page_start/page_end` 闭区间字段，不再新增 `page_range`、`pages`、`page_span`，读取历史产物时才做兼容。
- 前序摘要注入：后续学习阶段的 Pass1 能看到前序高频错点，辅助 `recurrence_hint` 判断。
- `qid_global = p{page}:{id}`：作为跨页、跨阶段、Pass2、L5、幻觉过滤和前端跳转的唯一题号，不得退回裸 `id`。
- `recurrence_hint`：保留 `new / recurring / na`，用于 L5 时序筛分。
- 课程标准三学段：按 `grade → stage` 参数化，避免固定四年级或第二学段。
- L4 校验闭环：学科 verifier 回写、幻觉过滤检测、纠错尝试、原文件 `*.corrected.bak` 备份和 `corrections_applied.json` 审计。
- L5 数字孪生体：`mastery_trajectory`、三区、演化叙事、证据链、兜底标记、thinking 落盘。
- L5 展示文本中文化：`evolution_narrative`、`rationale`、`suggested_next_step`、`error_clusters[*].cause` 必须是中文教育诊断表达，不得泄露 `session`、snake_case KP、英文枚举或模型链路字段。
- L5 evidence 净化：无观察项统一归一为 `no_observed` 且证据数组置空；真实分区证据只保留 evidence pack 中存在的 `qid_global`。
- Pass2 单产物收口：`zone_classification` 与 ontology 三区保持一致，逐题批语轻量生成。
- Pass3 双科交叉诊断：保留证据题号校验、空结果中文兜底、Markdown 汇总。
- 渲染增强：批改符号、题目框、全局题号角标、学习阶段横幅或等价可视化提示。

## nkcn 适配边界

允许的合理改进：

- 将批改主链路接入 nkcn 后台任务，并使用 `global_var.tasks`、`CIIndexManager`、`/api/ci/query|start|progress|result`。
- 使用 nkcn 用户文件解析、用户工作区、相对路径返回和 `/api/ci/layout_visual` 资产读取。
- 在 OCR markdown 不稳定或不可用时，用 `clean` 页面图做 LLM 兜底切分，但返回 schema 必须与本模块当前 schema 兼容。
- 为兼容历史批改产物，保留旧字段读取和空值兜底，但新产物应按本模块当前 schema 写入。
- 增加中文展示字段、中文术语映射、前端友好结构。

不允许的“适配”：

- 因接入麻烦而跳过 session、Pass1.5、verifier、hallucination、ontology、Pass2 或渲染任一关键阶段。
- 用裸英文标签直接给前端显示，或把内部 JSON 字段名作为 UI 文案。
- 新增硬编码 API key、个人代理、绝对缓存路径或生产服务器地址。

## UI 中文化要求

- UI 显示必须尽量使用中文。所有英文术语、内部字段名和枚举值在前端展示前都要翻译为中文。
- 允许后端内部 JSON schema 保留英文键名以兼容模型和代码，但接口结果应尽量提供中文映射，前端也必须使用映射后的中文值。
- 不要裸露这些内部字段名：`blind_spot`、`friction_zone`、`zpd`、`knowledge_point`、`qid_global`、`recurrence_hint`、`student_ontology`、`mastery_trajectory`、`session`、`fallback_used`、`built_by`、`confidence`、`trend`、`stability`。
- 推荐显示映射：
  - `blind_spot` → `盲区`
  - `friction_zone` → `内耗区`
  - `zpd` → `最近发展区`
  - `knowledge_point` → `知识点`
  - `qid_global` → `全局题号` 或直接显示为 `第N页·第X题`
  - `recurrence_hint` → `是否重复出现`
  - `new` → `新出现`
  - `recurring` → `反复出现`
  - `na` → `不适用`
  - `session` → `学习阶段` 或 `篇目`
  - `student_ontology` → `学科诊断结果`
  - `mastery_trajectory` → `掌握变化轨迹`
  - `fallback_used` → `已使用兜底`
  - `built_by` → `生成链路`
  - `confidence` → `置信度`
  - `trend` → `变化趋势`
  - `stability` → `稳定性`
  - `improving / stable / worsening` → `改善中 / 基本稳定 / 需关注`
  - `transient / persistent` → `阶段性 / 持续性`
- 面向教师/家长的页面标题也要保留本功能的认知三区口径：`blind_spot / friction_zone / zpd` 显示为“盲区 / 内耗区 / 最近发展区”，不要弱化成泛泛的“问题点/提升点”，也不要把“学习演化叙事”“学段 S2”或 `ontology_builder/deepseek...` 这类内部表达露给用户。
- AI 生成的自然语言正文也必须做展示前扫描：正文里的 `p{page}:{id}` 要替换为“第N页第X题”，正文里的 `session`、`ontology`、`L4/L5`、英文枚举或 snake_case 术语不得原样展示；若同一句已经出现“第N页第X题”，展示时可去掉“第M次练习”等时序字样以减轻阅读负担。证据 chip 可保留原始 qid 作为点击跳转值，但按钮文案仍要中文化。
- 批改进度文案也属于前端 UI，后端 `current_section` 与前端通知都不得裸露 `Session`、内部 session_id、`ontology`、`L4/L5` 等实现细节。
- 前端按钮、空状态、提示、进度、弹窗、图表轴、徽章都应使用中文；若确需展示模型名或文件名，可以保留原文。
- 后端 prompt 里要求模型输出英文规范标签是内部实现，不代表可以在 UI 上直接展示英文标签。展示知识点时优先使用 `label_to_cn_map` 或等价映射。

## 数据与产物

单次作业批改工作区应保持可排障结构：

```text
homework_grading/
  raw/
  clean/
  pass1_json/
  pass2_report/
  annotated/
  student_ontology.json
  student_ontology_evidence.json
  hallucination_report.json
  corrections_applied.json
  sample_meta.json
```

- `sample_meta.json` 必须包含学科、样本标识、年级、学段。
- `student_ontology_evidence.json.rule_baseline_profile` 是规则基线的默认归宿；若需要手动排障，可显式写入 `pass2_report/{sample}_rule_baseline_profile.json`，不得恢复 `student_profile.json` 作为对外并列综合产物。
- 课程标准与术语映射数据放在 `data/**`，新增数据要说明来源。
- 输出文件名要稳定、可追踪；thinking 文件名要能区分 Pass2、L5、Pass3。
- 读取历史产物时要兼容缺字段、空字符串、坏 JSON 和旧题号格式；写入新产物时按最新 schema。

## 模型与密钥

- Pass1/跨页修补优先使用本模块配置的 Qwen 模型；Qwen thinking 只在数学或复杂修补中打开。
- Qwen `extra_body.enable_thinking=True` 与 JSON Mode 互斥：此时禁止传 `response_format={"type":"json_object"}`；非 thinking 调用继续优先使用 JSON Mode，失败时再 fallback 到无 `response_format`。
- Qwen thinking 调用必须保留本地 JSON 解析兜底，至少兼容纯 JSON、Markdown 围栏 JSON、前后夹杂说明文字的首个 JSON 对象；不要为了修参数而改写 Pass1/Pass1.5 prompt 文本。
- Pass2、L5、Pass3、幻觉 retry 优先使用本模块配置的 DeepSeek 模型，复杂推理使用 `extra_body={"thinking":{"type":"enabled"},"reasoning_effort":"high"}`。
- 不要新增 `deepseek-chat`、`deepseek-reasoner` 等旧别名；修改模型调用后用 `rg "deepseek-chat|deepseek-reasoner"` 检查。
- API key 只能从环境变量或既有配置读取，例如 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY_ALI`、`DEEPSEEK_API_KEY`。不要在日志中打印完整密钥。
- 模型失败必须可降级：例如保留原 Pass1、跳过 retry、规则画像兜底、ontology 兜底，但要写入错误或审计信息。

## 修改流程

1. 先读 nkcn 当前模块和相关接口调用方。
2. 梳理影响范围：后端链路、API 返回、前端展示、文档是否需要同步。
3. 小范围修改，避免顺手重构超出当前问题的模块。
4. 同步更新 API 返回、前端中文展示或文档，确保不漏链路。
5. 更新 `djangoProject/docs/连续图片批改功能说明文档.md` 的“变更记录（倒序）”，最新记录放在最上方。
6. 用 `git status --short` 检查本次只包含相关文件。

## 验证建议

- 文档或本规范改动无需运行测试。
- 后端代码改动至少运行：

```bash
D:\postgraduate\nkcn-brain\djangoProject\nkcn\Scripts\python.exe manage.py check
```

- 纯函数或校验器改动优先补/跑最小测试；不要默认跑完整 LLM/OCR 重型链路。
- 涉及模型、课标或 prompt 时，至少做这些静态检查：
  - `rg "deepseek-chat|deepseek-reasoner" djangoProject/app_chat/homework_grading -g '!AGENTS.md'`
  - `rg "MA_4_|请批改这张第|题目或答案区域" djangoProject/app_chat/homework_grading/prompts.py djangoProject/app_chat/homework_grading/data/curriculum`
  - 运行 Qwen 调用参数离线回归，例如 `D:\postgraduate\nkcn-brain\djangoProject\nkcn\Scripts\python.exe -m unittest app_chat.homework_grading.qwen_api_regression_test`，确认 thinking 模式不传 `response_format`。
  - 检查前端是否仍裸露英文术语。
- 涉及 session 切分、L5、幻觉过滤、Pass3 时，要检查输出 JSON 和审计文件是否可读、证据题号是否真实存在。
