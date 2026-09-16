<template>
  <el-dialog :model-value="visible" title="批改材料设置" width="520px" class="feedback-material-dialog"
    :close-on-click-modal="false" @update:model-value="$emit('close')">
    <p class="material-file">{{ filename }}</p>
    <el-alert v-if="error" :title="error" type="error" :closable="false" />
    <el-form label-width="80px" :disabled="loading || submitting">
      <el-form-item label="学段">
        <el-select v-model="form.education_level" @change="preview">
          <el-option label="保持未知" value="" />
          <el-option v-for="(label, value) in levels" :key="value" :label="label" :value="value" />
        </el-select>
      </el-form-item>
      <el-form-item label="年级">
        <el-select v-model="form.grade" filterable allow-create clearable placeholder="可保持未知或填写年级" @change="preview">
          <el-option v-for="label in gradeOptions" :key="label" :label="label" :value="label" />
        </el-select>
      </el-form-item>
      <el-form-item label="课程">
        <el-input v-model="form.subject" placeholder="可填写未登记课程，或保持未知" @change="preview" />
      </el-form-item>
      <el-form-item label="材料类型">
        <el-select v-model="form.material_type" @change="preview">
          <el-option label="保持未知" value="" />
          <el-option v-for="label in ['作业', '试卷', '作文', '笔记', '日志']" :key="label" :label="label" :value="label" />
        </el-select>
      </el-form-item>
      <el-form-item label="课标">
        <el-select v-model="curriculumSelection">
          <el-option label="按材料自动匹配已有课标" value="auto" />
          <el-option label="不绑定课标" value="none" />
        </el-select>
      </el-form-item>
      <el-collapse>
        <el-collapse-item title="学期、教材与参考文字（可选）" name="optional">
          <el-form-item label="学期"><el-input v-model="form.term" @change="preview" /></el-form-item>
          <el-form-item label="教材"><el-input v-model="form.textbook" @change="preview" /></el-form-item>
          <el-form-item label="学制"><el-input v-model="form.school_system" placeholder="可保持未知" @change="preview" /></el-form-item>
          <el-form-item label="参考文字"><el-input v-model="referenceText" type="textarea" :rows="3" /></el-form-item>
          <p class="material-note">此处填写的文字会用于本次批改；勾选的其他文档和卡片暂不读取。</p>
        </el-collapse-item>
      </el-collapse>
    </el-form>
    <p v-if="candidate" class="material-note">将按：{{ candidate.education_level_name }} / {{ candidate.grade_label || '未知年级' }} / {{ candidate.subject_name || '未知课程' }} / {{ candidate.material_name || '未知类型' }} 批改</p>
    <el-alert v-for="warning in warnings" :key="warning" :title="warning" type="warning" :closable="false" />
    <p class="material-note">未注明的信息可以保持未知。启动后以服务器返回的材料信息为准。</p>
    <template #footer>
      <el-button :disabled="submitting" @click="$emit('close')">取消</el-button>
      <el-button type="primary" :loading="loading || submitting" :disabled="!!error" @click="submit">保存设置</el-button>
    </template>
  </el-dialog>
</template>

<script>
import { queryFeedbackMaterial, feedbackMaterialSettings } from '@/api/continuous_image'

export default {
  name: 'FeedbackMaterialDialog',
  props: { visible: Boolean, filename: String, username: String, sceneName: String, submitting: Boolean, initialContext: Object },
  emits: ['close', 'submit'],
  data() {
    return {
      form: {}, candidate: null, warnings: [], error: '', loading: false, eligible: false,
      requestSequence: 0, curriculumSelection: 'auto', referenceText: '',
      levels: { primary: '小学', junior: '初中', senior: '高中', vocational: '职业教育', university: '大学', postgraduate: '研究生', adult: '成人教育', other: '其他' },
    }
  },
  computed: {
    gradeOptions() {
      return ({ primary: ['一年级', '二年级', '三年级', '四年级', '五年级', '六年级'],
        junior: ['初一', '初二', '初三'], senior: ['高一', '高二', '高三'],
        university: ['大一', '大二', '大三', '大四'] })[this.form.education_level] || []
    },
  },
  watch: { visible: { immediate: true, handler(value) { if (value) this.initialize(); else this.requestSequence++ } } },
  methods: {
    overrides() {
      return Object.fromEntries(['education_level', 'grade', 'subject', 'material_type', 'term', 'textbook', 'school_system']
        .map(key => [key, this.form[key] || null]))
    },
    async initialize() {
      this.form = {}; this.candidate = null; this.error = ''; this.warnings = []
      this.curriculumSelection = 'auto'; this.referenceText = ''
      let saved
      try {
        saved = await feedbackMaterialSettings({ username: this.username, files: [this.filename] })
        if (saved.error_num !== 0) throw new Error(saved.msg)
      } catch (error) { this.error = error.message; return }
      const response = saved
      this.candidate = response.feedback_context; this.warnings = response.warnings || []
      this.curriculumSelection = saved.material?.curriculum_selection === null ? 'none' : 'auto'
      this.referenceText = saved.material?.reference_text || ''
      if (!response) return
      const context = this.initialContext || response.feedback_context
      const raw = context.declared_metadata?.selected_raw || {}
      this.form = { ...raw, education_level: context.education_level === 'unknown' ? '' : context.education_level,
        grade: raw.grade || '', subject: context.subject_name || '', material_type: context.material_name || '',
        term: context.term || '', textbook: context.textbook || '', school_system: context.school_system || '' }
      if (this.initialContext) await this.preview()
    },
    async preview(includeOverrides = true) {
      const sequence = ++this.requestSequence
      this.loading = true; this.error = ''
      try {
        const response = await queryFeedbackMaterial({ username: this.username, files: [this.filename], scene_name: this.sceneName,
          ...(includeOverrides === false ? {} : { feedback_overrides: this.overrides() }) })
        if (sequence !== this.requestSequence) return null
        if (response.error_num !== 0) throw new Error(response.msg || '材料解析失败')
        this.candidate = response.feedback_context
        this.warnings = response.warnings || []
        this.eligible = response.feedback_eligible
        return response
      } catch (error) {
        if (sequence === this.requestSequence) { this.error = error.message || '材料解析失败'; this.eligible = false }
        return null
      } finally { if (sequence === this.requestSequence) this.loading = false }
    },
    async submit() {
      const response = await this.preview()
      if (!response) return
      this.$emit('submit', { feedback_overrides: this.overrides(),
        curriculum_selection: this.curriculumSelection === 'none' ? null : 'auto', reference_text: this.referenceText })
    },
  },
}
</script>

<style>
.feedback-material-dialog { max-width: calc(100vw - 24px); }
.feedback-material-dialog .el-select { width: 100%; }
.feedback-material-dialog .material-file { overflow-wrap: anywhere; margin-top: 0; }
.feedback-material-dialog .material-note { color: #606266; font-size: 12px; line-height: 1.6; }
.feedback-material-dialog .el-alert { margin-bottom: 10px; }
</style>
