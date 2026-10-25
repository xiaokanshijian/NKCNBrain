<template>
  <section class="feedback-basis-strip">
    <strong>本版本材料依据</strong>
    <p v-if="context">{{ context.education_level_name || '未知学段' }} · {{ context.grade_label || '未知年级' }} · {{ context.subject_name || '未知课程' }} · {{ context.material_name || '未知类型' }}</p>
    <p v-else>此版本未保存可恢复的材料信息，原结果仍可查看。</p>
    <p v-if="context">{{ context.curriculum_binding ? `已绑定课标 · 版本 ${context.curriculum_binding.version}` : '未绑定课标' }}</p>
    <p>材料核对：{{ observationLabel }}<span v-if="coverage">（{{ coverage }}）</span></p>
    <el-alert v-if="error" :title="`${failureLabel}：${error}`" type="error" :closable="false" />
    <el-alert v-for="warning in allWarnings" :key="warning" :title="warning" type="warning" :closable="false" />
    <details>
      <summary>查看本版本依据与观察记录</summary>
      <p>依据状态：{{ snapshotLabel }}</p>
      <p v-for="rule in context?.skill_bindings || []" :key="rule.id">{{ ruleLabel(rule.id) }} · {{ rule.version }}</p>
      <p v-for="(item, index) in observation.evidence || []" :key="index">
        {{ item.page ? `第${item.page}页` : '尚未确认页码' }} · {{ item.source === 'page_header' ? '页面标题' : '已有文字识别' }}：{{ item.excerpt }}
      </p>
      <p v-if="runId">运行编号：<code>{{ runId }}</code></p>
      <p v-if="fingerprint">依据指纹：<code>{{ fingerprint }}</code></p>
    </details>
  </section>
</template>

<script>
export default {
  name: 'FeedbackBasisStrip',
  props: { result: Object, task: Object },
  computed: {
    context() { return this.result?.feedback_context || (!this.result ? this.task?.feedback_context : null) },
    observation() { return (this.result ? this.result.content_validation : this.task?.content_validation) || { status: 'inconclusive' } },
    observationLabel() { return ({ conflict: '有差异，待核对', consistent: '已核对部分明确文字', inconclusive: '证据不足，尚不能确认' })[this.observation.status] || '尚不能确认' },
    coverage() {
      const coverage = this.observation.coverage
      if (!coverage) return ''
      return coverage.expected_pages ? `已观察${coverage.pages?.length || 0}/${coverage.expected_pages}页` : '页码范围尚未确认'
    },
    allWarnings() { return [...new Set([...((this.result ? this.result.warnings : this.task?.warnings) || []), ...(this.result?.snapshot_warnings || [])])] },
    error() { return this.result?.manifest?.error || (!this.result ? this.task?.error : '') || '' },
    failureLabel() {
      const stage = this.result?.failure_stage || this.task?.failure_stage
      return ({ startup: '启动失败', preprocess: '页面预处理失败', sessions: '篇目识别失败', layout: '版面识别失败', understanding: '理解失败', grading: '批改失败', cross_page: '跨页处理失败', review: '复核失败', verification: '规则校验失败', memory: '线索汇总失败', ontology: '学习诊断失败', report: '报告生成失败', hallucination: '结果复核失败', render: '批改图生成失败', quality: '质量评分失败', output_validation: '产物校验失败', interrupted: '执行中断', recovery: '恢复检查失败' })[stage] || '执行失败'
    },
    snapshotLabel() {
      return ({ complete: '已冻结，可恢复', legacy_missing: '旧版本未保存', invalid: '依据损坏', missing: '依据文件缺失', incomplete: '依据不完整', unsupported: '格式暂不支持' })[this.result?.snapshot_status] || (this.context ? '本次依据已冻结' : '未保存')
    },
    runId() { return this.result ? this.result.manifest?.run_id : this.task?.run_id },
    fingerprint() { return this.result ? this.result.config_fingerprint : this.task?.config_fingerprint },
  },
  methods: {
    ruleLabel(id) {
      return ({ 'question-generic': '通用题目规则', 'generic-question': '通用题目规则', 'math-primary4-question': '四年级数学专项', 'chinese-primary4-question': '四年级语文专项', 'english-primary4-question': '四年级英语专项' })[id] || '题目批改规则'
    },
  },
}
</script>

<style scoped>
.feedback-basis-strip { background: #f7f9fc; border: 1px solid #dce3ed; border-radius: 8px; padding: 12px; margin-bottom: 14px; font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.feedback-basis-strip p { margin: 5px 0; }
.feedback-basis-strip summary { cursor: pointer; color: #385779; }
.feedback-basis-strip .el-alert { margin: 8px 0; }
.feedback-basis-strip code { font-size: 11px; word-break: break-all; }
</style>
